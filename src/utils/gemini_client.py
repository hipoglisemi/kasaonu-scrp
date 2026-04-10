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
    retry_delay: float = 5.0, # Linear delay between keys
    **kwargs: Any
) -> str:
    """
    Sends prompt to Gemini API with a simple Linear Loop.
    1. Tries keys 0 to N in fixed order.
    2. Waits 5s between keys if Rate Limited (429/503).
    3. Gives up if all keys are exhausted in one round.
    """
    if not HAS_GENAI:
        raise ImportError("google-genai kütüphanesi yüklü değil.")

    model_name = model or os.getenv("GEMINI_MODEL", "gemini-3.1-flash-lite-preview")
    
    if "config" in kwargs:
        config = kwargs.pop("config")
    else:
        config = _types.GenerateContentConfig(**kwargs) if kwargs else None

    keys = _load_keys()
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
            if idx > 0:
                print(f"[KeyLoop] ✨ Success with Key #{idx + 1} (Total keys: {len(keys)})")
            return response.text.strip()

        except Exception as e:
            err_str = str(e).lower()
            is_retriable = any(
                token in err_str
                for token in ["429", "resourceexhausted", "quota", "rate_limit", "500", "502", "503", "504", "deadline_exceeded"]
            )
            
            if is_retriable:
                # 503 High Demand requires longer wait
                is_503 = "503" in err_str or "high demand" in err_str
                current_delay = retry_delay * 2 if is_503 else retry_delay
                # Add jitter
                current_delay += random.uniform(0, 2)
                
                msg = f"[KeyLoop] ⚠️  Key #{idx + 1} failed ({type(e).__name__})."
                if idx + 1 < len(keys):
                    print(f"{msg} {'(MODEL HIGH DEMAND)' if is_503 else ''} Trying next key... ({idx + 2}/{len(keys)}) | Waiting {current_delay:.1f}s...")
                    time.sleep(current_delay)
                else:
                    print(f"{msg} All {len(keys)} keys exhausted.")
                last_error = e
                continue # Try next key
            else:
                # Fatal error
                print(f"[KeyLoop] ❌ Fatal Error with Key #{idx + 1}: {e}")
                raise

    raise RuntimeError(f"Tüm Gemini API anahtarları ({len(keys)} adet) denendi fakat başarısız oldu. Son hata: {last_error}")


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
