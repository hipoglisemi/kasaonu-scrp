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


# ─── Single generate call with Patient Sequential System ────────────────────────
def generate_with_rotation(
    prompt: str,
    model: Optional[str] = None,
    retry_delay: float = 5.0, # Reduced from 20.0 to 5.0s
    **kwargs: Any
) -> str:
    """
    Sends prompt to Gemini API with the Patient Sequential System.
    1. Tries keys in fixed order (Key 0 -> Key 7).
    2. Waits 20s between keys if Rate Limited (429/503).
    3. If all keys fail, waits 60s and tries again (up to 5 global attempts).
    """
    if not HAS_GENAI:
        raise ImportError("google-genai kütüphanesi yüklü değil.")

    model_name = model or os.getenv("GEMINI_MODEL", "gemini-3.1-flash-lite-preview")
    
    if "config" in kwargs:
        config = kwargs.pop("config")
    else:
        config = _types.GenerateContentConfig(**kwargs) if kwargs else None

    keys = _load_keys()
    max_global_attempts = 5
    
    for g_attempt in range(max_global_attempts):
        last_error: Optional[Exception] = None
        
        for idx, key in enumerate(keys):
            try:
                client = _sdk.Client(api_key=key)
                response = client.models.generate_content(
                    model=model_name,
                    contents=prompt,
                    config=config
                )
                
                # Success Log
                if g_attempt > 0 or idx > 0:
                    print(f"[KeySequencer] ✨ Success (Key #{idx + 1}, Global attempt {g_attempt + 1})")
                return response.text.strip()

            except Exception as e:
                err_str = str(e).lower()
                is_retriable = any(
                    token in err_str
                    for token in ["429", "resourceexhausted", "quota", "rate_limit", "500", "502", "503", "504", "deadline_exceeded"]
                )
                
                if is_retriable:
                    msg = f"[KeySequencer] ⚠️  Key #{idx + 1} failed ({type(e).__name__})."
                    if idx + 1 < len(keys):
                        print(f"{msg} Trying next key... ({idx + 2}/{len(keys)}) | Waiting {retry_delay}s...")
                        time.sleep(retry_delay)
                    else:
                        print(f"{msg} All {len(keys)} keys exhausted for this round.")
                    last_error = e
                    continue # Try next key
                else:
                    # Fatal error
                    print(f"[KeySequencer] ❌ Fatal Error with Key #{idx + 1}: {e}")
                    raise

        # If all keys exhausted in this round
        if g_attempt + 1 < max_global_attempts:
            wait_time = 60.0
            print(f"[KeySequencer] 🚨 All {len(keys)} keys exhausted. Global cooling for {wait_time}s... (Attempt {g_attempt + 1}/{max_global_attempts})")
            time.sleep(wait_time)
        else:
            raise RuntimeError(f"Tüm Gemini API anahtarları ({len(keys)} adet) {max_global_attempts} tur denendi fakat başarısız oldu. Son hata: {last_error}")

    return "" # Should not reach here


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
