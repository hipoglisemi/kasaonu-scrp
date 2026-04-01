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


# ─── Load keys dynamically from environment ───────────────────────────────
def _load_keys() -> List[str]:
    """
    Finds all environment variables starting with GEMINI_API_KEY.
    Returns a unique list of non-empty API keys.
    """
    keys = []
    # Identify all possible keys in the environment (GEMINI_API_KEY, GEMINI_API_KEY_1, ..., GEMINI_API_KEY_N)
    for env_key, value in os.environ.items():
        if env_key.startswith("GEMINI_API_KEY"):
            k = value.strip()
            # Clean possible quotes
            if k.startswith('"') and k.endswith('"'): k = k[1:-1]
            if k.startswith("'") and k.endswith("'"): k = k[1:-1]
            if k and k not in keys:
                keys.append(k)
    
    if not keys:
        raise ValueError(
            "Hiç Gemini API anahtarı bulunamadı. "
            "Lütfen .env dosyasında GEMINI_API_KEY_... değişkenlerini tanımlayın."
        )
    return keys


# ─── Single generate call with Shuffle Rotation ──────────────────────────────
def generate_with_rotation(
    prompt: str,
    model: Optional[str] = None,
    retry_delay: float = 3.0,
    **kwargs: Any
) -> str:
    """
    Sends prompt to Gemini API with automatic key rotation and randomization.
    Distributes load across all available keys by shuffling at each request.
    """
    if not HAS_GENAI:
        raise ImportError("google-genai kütüphanesi yüklü değil.")

    model_name = model or os.getenv("GEMINI_MODEL", "gemini-3.1-flash-lite-preview")
    
    # Extract config if present
    if "config" in kwargs:
        config = kwargs.pop("config")
    else:
        config = _types.GenerateContentConfig(**kwargs) if kwargs else None

    # Load and SHUFFLE keys to distribute weight
    keys = _load_keys()
    random.shuffle(keys)
    
    last_error: Optional[Exception] = None

    for idx, key in enumerate(keys):
        try:
            client = _sdk.Client(api_key=key)
            response = client.models.generate_content(
                model=model_name,
                contents=prompt,
                config=config
            )
            # Log successful rotation if it wasn't the first try
            if idx > 0:
                print(f"[KeyRotation] ✨ Success with Key #{idx + 1} (Total available keys: {len(keys)})")
            return response.text.strip()

        except Exception as e:
            err_str = str(e).lower()
            # Catch Rate Limits and Server Errors (Retriable)
            is_retriable = any(
                token in err_str
                for token in ["429", "resourceexhausted", "quota", "rate_limit", "500", "502", "503", "504", "deadline_exceeded"]
            )
            
            if is_retriable:
                print(
                    f"[KeyRotation] ⚠️  Key #{idx + 1} failed ({type(e).__name__}). "
                    + (f"Trying next key... ({idx + 2}/{len(keys)})" if idx + 1 < len(keys) else "No more keys!")
                )
                last_error = e
                time.sleep(retry_delay)
                continue  # Try next key
            else:
                # Fatal errors (400 Invalid Argument, etc.) should not be retried with other keys
                print(f"[KeyRotation] ❌ Fatal Error with Key #{idx + 1}: {e}")
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
