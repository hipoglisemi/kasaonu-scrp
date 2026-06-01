import os
import time
import random
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
    """
    all_env_keys = [k for k in os.environ.keys() if k.startswith("GEMINI_API_KEY")]
    
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


# ─── Single generate call with Linear Loop System ────────────────────────
def generate_with_rotation(
    prompt: str,
    model: Optional[str] = None,
    fallback_model: Optional[str] = None,
    retry_delay: float = 5.0, # Linear delay between keys
    **kwargs: Any
) -> str:
    """
    Sends prompt to Gemini API with a simple Linear Loop and optional fallback model.
    1. Tries keys 0 to N in fixed order with the primary model.
    2. Waits 5s between keys if Rate Limited (429/503).
    3. If all keys fail and fallback_model is provided, repeats the loop with the fallback model.
    """
    if not HAS_GENAI:
        raise ImportError("google-genai kütüphanesi yüklü değil.")

    primary_model_name = model or os.getenv("GEMINI_MODEL", "gemini-3.1-flash-lite")
    fallback_model_name = fallback_model or os.getenv("FALLBACK_MODEL")
    
    # 🎯 AUTOMATIC GEMINI-3.1-FLASH-LITE -> GEMMA-4-31B-IT FALLBACK RULE
    if "gemini-3.1-flash-lite" in primary_model_name.lower() and not fallback_model_name:
        fallback_model_name = "models/gemma-4-31b-it"
        print(f"[KeyLoop] 🛡️ Automatic Fallback Armed: gemini-3.1-flash-lite -> {fallback_model_name}")
    
    models_to_try = [(primary_model_name, "Primary")]
    if fallback_model_name:
        models_to_try.append((fallback_model_name, "Fallback"))
    
    if "config" in kwargs:
        config = kwargs.pop("config")
    else:
        config = _types.GenerateContentConfig(**kwargs) if kwargs else None

    keys = _load_keys()
    
    # Pair keys with their original 1-based index
    indexed_keys = [{"value": val, "original_index": i + 1} for i, val in enumerate(keys)]
    
    reverse_keys = False
    # Check if a custom subset of 1-based key indices is specified (e.g. key_indices=[8, 7])
    key_indices = kwargs.pop("key_indices", None)
    if key_indices:
        indexed_keys = [ik for idx in key_indices for ik in indexed_keys if ik["original_index"] == idx]
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
                    
                    # Success Log
                    if idx > 0 or model_role == "Fallback" or reverse_keys or attempt > 1:
                        print(f"[KeyLoop] ✨ Success with Key #{orig_idx} using {model_role} model ({current_model}) (Global Attempt {attempt}/{max_global_attempts})")
                    return response.text.strip()

                except Exception as e:
                    err_str = str(e).lower()
                    is_retriable = any(
                        token in err_str
                        for token in ["429", "resourceexhausted", "quota", "rate_limit", "500", "502", "503", "504", "deadline_exceeded"]
                    )
                    
                    if is_retriable:
                        # Tüm anahtarlar sırayla denensin, sadece hepsi tükenince fallback'e geç.
                        # (Önceki "anında atla" kuralı kaldırıldı — 3 key varsa hepsini dene!)
                        
                        # 503 High Demand requires longer wait
                        is_503 = "503" in err_str or "high demand" in err_str
                        current_delay = retry_delay * 2 if is_503 else retry_delay
                        # Add jitter
                        current_delay += random.uniform(0, 2)
                        
                        msg = f"[KeyLoop] ⚠️  Key #{orig_idx} failed for {current_model} ({type(e).__name__})."
                        if idx + 1 < len(indexed_keys):
                            next_orig_idx = indexed_keys[idx + 1]["original_index"]
                            print(f"{msg} {'(HIGH DEMAND)' if is_503 else ''} Trying next key... (Key #{next_orig_idx}) | Waiting {current_delay:.1f}s...")
                            time.sleep(current_delay)
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

    keys = _load_keys()
    key = random.choice(keys)
    return _sdk.Client(api_key=key)
