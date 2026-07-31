import os
import time
import random
import json
from typing import Optional, Union, List, Any
try:
    from dotenv import load_dotenv # type: ignore
except ImportError:
    def load_dotenv(*args, **kwargs): pass

# Find project root
_root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
load_dotenv(os.path.join(_root, ".env"), override=True)

# SDK imports with type hinting safety
try:
    from google import genai as _sdk  # type: ignore
    from google.genai import types as _types  # type: ignore
    HAS_GENAI = True
except ImportError:
    HAS_GENAI = False


# ─── Load keys dynamically from environment (Sorted Order) ─────────────────
def _load_keys() -> List[str]:
    """
    Finds all GEMINI_API_KEY environment variables and returns them in a fixed order.
    Original GEMINI_API_KEY comes first, then _1, _2, etc.
    NOTE: GEMINI_PROACTIVE_API_KEY is explicitly excluded so scrapers never consume proactive keys.
    """
    all_env_keys = [k for k in os.environ.keys() if k.startswith("GEMINI_API_KEY") and not k.startswith("GEMINI_PROACTIVE")]
    
    # 🛡️ PROTECT TIER-1 KEY: Never allow the base GEMINI_API_KEY (paid key) for any scrapers/scripts.
    # All scripts (including proactive audit) must only use rotation/free keys (GEMINI_API_KEY_1, _2, etc.)
    if "GEMINI_API_KEY" in all_env_keys:
        all_env_keys.remove("GEMINI_API_KEY")
    
    # Sort keys to ensure stable order: GEMINI_API_KEY, then GEMINI_API_KEY_1, _2, etc.
    def sort_key(k):
        if k == "GEMINI_API_KEY": return 0
        try: return int(k.split("_")[-1])
        except: return 999

    sorted_env_keys = sorted(all_env_keys, key=sort_key)
    
    keys = []
    for env_key in sorted_env_keys:
        value = os.environ.get(env_key, "").strip()
        if not value: continue
        
        # Clean possible quotes
        if value.startswith('"') and value.endswith('"'): value = value[1:-1]
        if value.startswith("'") and value.endswith("'"): value = value[1:-1]
        
        if value and value not in keys:
            keys.append(value)
    
    if not keys:
        raise ValueError("Hiç Gemini API anahtarı bulunamadı.")
    return keys


def load_proactive_keys() -> List[str]:
    """
    Dedicated key loader for Proactive Expiry Audit (GEMINI_PROACTIVE_API_KEY).
    Isolated exclusively for proactive audit runs so scrapers never touch this key.
    """
    proactive_keys = [k for k in os.environ.keys() if k.startswith("GEMINI_PROACTIVE_API_KEY")]
    keys = []
    for k in sorted(proactive_keys):
        value = os.environ.get(k, "").strip()
        if not value: continue
        if value.startswith('"') and value.endswith('"'): value = value[1:-1]
        if value.startswith("'") and value.endswith("'"): value = value[1:-1]
        if value and value not in keys:
            keys.append(value)
            
    if not keys:
        print("⚠️ [Proactive Key Alert] GEMINI_PROACTIVE_API_KEY not found in environment. Falling back to default scraper key pool.")
        return _load_keys()
    
    return keys


# ─── Single generate call with Linear Loop System ────────────────────────
def generate_with_rotation(
    prompt: str,
    model: Optional[str] = None,
    fallback_model: Optional[str] = None,
    retry_delay: float = 5.0, # Linear delay between keys
    **kwargs: Any
) -> str:
    text, _ = _generate_internal(prompt, model, fallback_model, retry_delay, **kwargs)
    return text

def generate_with_rotation_tracked(
    prompt: str,
    model: Optional[str] = None,
    fallback_model: Optional[str] = None,
    retry_delay: float = 5.0,
    **kwargs: Any
):
    """Same as generate_with_rotation but also returns (text, usage_dict).
    usage_dict has keys: input_tokens, output_tokens
    """
    return _generate_internal(prompt, model, fallback_model, retry_delay, **kwargs)

def _generate_internal(
    prompt: str,
    model: Optional[str] = None,
    fallback_model: Optional[str] = None,
    retry_delay: float = 5.0,
    **kwargs: Any
):
    """Core implementation — returns (text, usage_dict)."""
    if not HAS_GENAI:
        raise ImportError("google-genai kütüphanesi yüklü değil.")

    primary_model_name = model or os.getenv("GEMINI_MODEL", "gemini-3.5-flash-lite")
    fallback_model_name = fallback_model or os.getenv("FALLBACK_MODEL")
    
    # 🎯 AUTOMATIC GEMINI-3.5-FLASH-LITE -> GEMMA-4-31B-IT FALLBACK RULE
    if "gemini-3.5-flash-lite" in primary_model_name.lower() and not fallback_model_name:
        fallback_model_name = "models/gemma-4-31b-it"
        print(f"[KeyLoop] 🛡️ Automatic Fallback Armed: gemini-3.5-flash-lite -> {fallback_model_name}")
    
    models_to_try = [(primary_model_name, "Primary")]
    if fallback_model_name:
        models_to_try.append((fallback_model_name, "Fallback"))
    
    if "config" in kwargs:
        config = kwargs.pop("config")
    else:
        config = _types.GenerateContentConfig(**kwargs) if kwargs else None

    override_keys = kwargs.pop("override_keys", None)
    keys = override_keys if override_keys else _load_keys()
    
    # Pair keys with their original 1-based index
    indexed_keys = [{"value": val, "original_index": i + 1} for i, val in enumerate(keys)]
    
    reverse_keys = False
    # Check if a custom subset of 1-based key indices is specified (e.g. key_indices=[8, 7])
    key_indices = kwargs.pop("key_indices", None)
    if key_indices:
        num_keys = len(indexed_keys)
        if num_keys > 0:
            valid_indices = [((idx - 1) % num_keys) + 1 for idx in key_indices]
            indexed_keys = [ik for idx in valid_indices for ik in indexed_keys if ik["original_index"] == idx]
        else:
            indexed_keys = []
    else:
        # Check for reverse keys env
        reverse_keys = os.getenv("REVERSE_KEYS", "False").lower() == "true"
        if reverse_keys:
            indexed_keys = list(reversed(indexed_keys))
            print(f"[KeyLoop] 🔀 Running in Reverse Key Order (Starting from Key #{indexed_keys[0]['original_index']} down to Key #{indexed_keys[-1]['original_index']})...")
        
    last_error: Optional[Exception] = None
    max_global_attempts = 5  # Tüm keylerin sırayla taranacağı maksimum tur sayısı
    
    for attempt in range(1, max_global_attempts + 1):
        for current_model, model_role in models_to_try:
            if model_role == "Fallback":
                print(f"[KeyLoop] 🔄 Switching immediately to Fallback model: {current_model}")
                
            for idx, key_info in enumerate(indexed_keys):
                key = key_info["value"]
                orig_idx = key_info["original_index"]
                try:
                    client = _sdk.Client(api_key=key)
                    response = client.models.generate_content(
                        model=current_model,
                        contents=prompt,
                        config=config
                    )
                    
                    # Parse usage metadata if available
                    usage = {"input_tokens": 0, "output_tokens": 0}
                    try:
                        meta = getattr(response, "usage_metadata", None)
                        if meta:
                            usage["input_tokens"] = getattr(meta, "prompt_token_count", 0) or 0
                            usage["output_tokens"] = getattr(meta, "candidates_token_count", 0) or 0
                    except Exception:
                        pass
                    
                    # Success Log
                    if idx > 0 or model_role == "Fallback" or reverse_keys or attempt > 1:
                        print(f"[KeyLoop] ✨ Success with Key #{orig_idx} using {model_role} model ({current_model}) (Global Attempt {attempt}/{max_global_attempts})")
                    return response.text.strip(), usage

                except Exception as e:
                    err_str = str(e).lower()
                    is_retriable = any(
                        token in err_str
                        for token in ["429", "resourceexhausted", "quota", "rate_limit", "500", "502", "503", "504", "deadline_exceeded"]
                    )
                    
                    if is_retriable:
                        # Tüm anahtarlar sırayla denensin, sadece hepsi tükenince fallback'e geç.
                        # (Önceki "anında atla" kuralı kaldırıldı — 3 key varsa hepsini dene!)
                        
                        is_quota_or_depleted = any(x in err_str for x in ["quota", "depleted", "limit", "429"])
                        is_503 = "503" in err_str or "high demand" in err_str
                        
                        # Farklı bir API anahtarına geçtiğimiz için gereksiz yere beklemeyi engelliyoruz.
                        if is_quota_or_depleted:
                            current_delay = 0.0
                        elif is_503:
                            current_delay = 2.0 + random.uniform(0, 1)
                        else:
                            current_delay = 0.1
                        
                        msg = f"[KeyLoop] ⚠️  Key #{orig_idx} failed for {current_model} ({type(e).__name__})."
                        if idx + 1 < len(indexed_keys):
                            next_orig_idx = indexed_keys[idx + 1]["original_index"]
                            if current_delay > 0:
                                print(f"{msg} {'(HIGH DEMAND)' if is_503 else ''} Trying next key... (Key #{next_orig_idx}) | Waiting {current_delay:.1f}s...")
                                time.sleep(current_delay)
                            else:
                                print(f"{msg} Trying next key immediately... (Key #{next_orig_idx})")
                        else:
                            print(f"{msg} All {len(indexed_keys)} keys exhausted for {current_model} in this loop.")
                        last_error = e
                        continue # Try next key
                    else:
                        # Fatal error — hemen fırlat
                        print(f"[KeyLoop] ❌ Fatal Error with Key #{orig_idx} on {current_model}: {e}")
                        raise

        
        # Eğer tüm keyler tükendiyse ve hala deneme hakkımız varsa, pes etme! Uyu ve başa dön.
        if attempt < max_global_attempts:
            cooldown = 15.0 + random.uniform(0, 5)
            print(f"\n[KeyLoop] 🚨 All {len(indexed_keys)} API keys failed (probably IP-based rate limit). Sleeping for {cooldown:.1f}s before global retry {attempt + 1}/{max_global_attempts}...\n")
            time.sleep(cooldown)

    raise RuntimeError(f"Tüm Gemini API anahtarları ({len(indexed_keys)} adet) {max_global_attempts} tur denendi fakat başarısız oldu. Son hata: {last_error}")


# ─── API Studio Client Helper ────────────────────────────────────
def get_gemini_client() -> Any:
    """
    Returns a client initialized with a random key from the pool.
    """
    if not HAS_GENAI:
        raise ImportError("google-genai kütüphanesi yüklü değil.")
    keys = load_proactive_keys()
    return _sdk.Client(api_key=keys[0])


# ─── Gemini Batch API Helper Functions (%50 Discount) ────────────────────────
def submit_proactive_batch_job(
    requests_list: List[dict],
    model: str = "gemini-3.5-flash-lite",
    batch_filename: str = "proactive_audit_batch.jsonl"
) -> Any:
    """
    Submits a batch job to Google AI Studio Batch API (%50 cost discount).
    requests_list: List of dicts formatted with custom_id and request parameters.
    """
    if not HAS_GENAI:
        raise ImportError("google-genai kütüphanesi yüklü değil.")
    
    proactive_keys = load_proactive_keys()
    client = _sdk.Client(api_key=proactive_keys[0])
    
    # Save requests to JSONL
    with open(batch_filename, "w", encoding="utf-8") as f:
        for item in requests_list:
            f.write(json.dumps(item, ensure_ascii=False) + "\n")
            
    print(f"📦 [Batch API] Packaged {len(requests_list)} requests into '{batch_filename}'. Uploading to Google AI Studio...")
    
    uploaded_file = client.files.upload(
        file=batch_filename,
        config=_types.UploadFileConfig(mime_type="text/plain")
    )
    print(f"✅ [Batch API] File uploaded successfully: {uploaded_file.name}")
    
    batch_job = client.batches.create(
        model=model,
        src=uploaded_file.name
    )
    print(f"🚀 [Batch API] Batch Job submitted successfully!")
    print(f"   🆔 Job Name: {batch_job.name}")
    print(f"   📊 Initial State: {batch_job.state}")
    
    return batch_job, uploaded_file.name


def poll_and_download_batch_results(
    batch_job_name: str,
    max_wait_seconds: int = 1500,
    check_interval: int = 25
) -> dict:
    """
    Polls Gemini Batch API until completion (SUCCEEDED/FAILED) and returns parsed dict by custom_id.
    """
    if not HAS_GENAI:
        raise ImportError("google-genai kütüphanesi yüklü değil.")
        
    proactive_keys = load_proactive_keys()
    client = _sdk.Client(api_key=proactive_keys[0])
    
    start_time = time.time()
    print(f"⏳ [Batch API Polling] Waiting for Batch Job '{batch_job_name}' to complete (Max wait: {max_wait_seconds/60:.1f} mins)...")
    
    while time.time() - start_time < max_wait_seconds:
        job = client.batches.get(name=batch_job_name)
        state_str = str(job.state).upper()
        elapsed_mins = (time.time() - start_time) / 60
        
        if "SUCCEEDED" in state_str:
            print(f"🎉 [Batch API Success] Job completed successfully in {elapsed_mins:.1f} mins!")
            dest_obj = getattr(job, "dest", None)
            output_file_name = None
            if dest_obj:
                if hasattr(dest_obj, "file_name") and dest_obj.file_name:
                    output_file_name = dest_obj.file_name
                elif isinstance(dest_obj, str):
                    output_file_name = dest_obj
            if not output_file_name:
                output_file_name = getattr(job, "output_file_name", None)
            
            if not output_file_name:
                raise RuntimeError(f"Batch Job succeeded but no output file path could be extracted. Job: {job}")
                
            print(f"📥 [Batch API Download] Downloading output file '{output_file_name}'...")
            file_content = client.files.download(file=output_file_name)
            lines = file_content.decode("utf-8").splitlines()
            
            results_map = {}
            for line in lines:
                if not line.strip(): continue
                try:
                    data = json.loads(line.strip())
                    custom_id = data.get("custom_id")
                    if custom_id:
                        results_map[custom_id] = data
                except Exception as e:
                    print(f"⚠️ [Batch API Line Parse Error]: {e}")
                    
            print(f"✅ [Batch API Download] Successfully downloaded and parsed {len(results_map)} campaign responses!")
            return results_map
            
        elif "FAILED" in state_str or "CANCELLED" in state_str:
            raise RuntimeError(f"🚨 [Batch API Error] Job failed or cancelled with state: {job.state} | Error: {getattr(job, 'error', None)}")
            
        print(f"   ⏳ [Batch API Polling] State: {job.state} | Elapsed: {elapsed_mins:.1f} mins | Retrying in {check_interval}s...")
        time.sleep(check_interval)
        
    raise TimeoutError(f"⏰ [Batch API Timeout] Job did not complete within {max_wait_seconds/60:.1f} minutes.")


    keys = _load_keys()
    key = random.choice(keys)
    return _sdk.Client(api_key=key)
