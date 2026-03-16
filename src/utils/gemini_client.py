import os
import time
from typing import Optional, Union, List, Any
try:
    from dotenv import load_dotenv # type: ignore
except ImportError:
    def load_dotenv(*args, **kwargs): pass

# Find project root
_root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
load_dotenv(os.path.join(_root, ".env"), override=True)

# SDK importlarını tip ipuçları için en üstte ama güvenli (try-except) şekilde tutalım.
# Eğer yüklü değilse çalışma anında hata vermemesi için fonksiyon içinde asıl kullanım yapılır.
try:
    from google import genai as _sdk  # type: ignore
    from google.genai import types as _types  # type: ignore
    HAS_GENAI = True
except ImportError:
    HAS_GENAI = False


# ─── Key listesini ortam değişkenlerinden oku ───────────────────────────────
def _load_keys() -> List[str]:
    keys = []
    for name in ["GEMINI_API_KEY", "GEMINI_API_KEY_1", "GEMINI_API_KEY_2"]:
        k = os.getenv(name, "").strip()
        if k:
            keys.append(k)
    if not keys:
        raise ValueError(
            "Hiç Gemini API anahtarı bulunamadı. "
            "GEMINI_API_KEY, GEMINI_API_KEY_1 veya GEMINI_API_KEY_2 env değişkenlerinden "
            "en az birini tanımlayın."
        )
    return keys


# ─── Tek bir generate çağrısı (key döngüsüyle) ──────────────────────────────
def generate_with_rotation(
    prompt: str,
    model: Optional[str] = None,
    retry_delay: float = 5.0,
    **kwargs: Any
) -> str:
    """
    Verilen prompt'u Gemini API'ye gönderir.
    Sadece key rotation ile çalışır.
    """
    if not HAS_GENAI:
        raise ImportError("google-genai kütüphanesi yüklü değil.")

    model_name = model or os.getenv("GEMINI_MODEL", "gemini-3.1-flash-lite-preview")
    
    # Wrap direct parameters into config object
    if "config" in kwargs:
        config = kwargs.pop("config")
    else:
        config = _types.GenerateContentConfig(**kwargs) if kwargs else None

    # AI Studio / Key Rotation Mode
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
            if idx > 0:
                print(f"[KeyRotation] Anahtar #{idx + 1} başarılı ({model_name}).")
            return response.text.strip()

        except Exception as e:
            err_str = str(e).lower()
            is_rate_limit = any(
                token in err_str
                for token in ["429", "resourceexhausted", "quota", "rate_limit", "rateerror"]
            )
            if is_rate_limit:
                print(
                    f"[KeyRotation] ⚠️  Anahtar #{idx + 1} limit doldu "
                    f"({type(e).__name__}). "
                    + (f"Anahtar #{idx + 2}'ye geçiliyor..." if idx + 1 < len(keys) else "Başka anahtar yok!")
                )
                last_error = e
                time.sleep(retry_delay)
                continue  # sonraki key
            else:
                raise
    
    raise RuntimeError(f"Tüm Gemini API anahtarları tükendi. Son hata: {last_error}")


# ─── API Studio İstemcisi ────────────────────────────────────
def get_gemini_client() -> Any:
    """
    AI Studio: ilk geçerli anahtarı kullan
    """
    if not HAS_GENAI:
        raise ImportError("google-genai kütüphanesi yüklü değil.")

    # AI Studio: ilk geçerli anahtarı kullan
    key = _load_keys()[0]
    return _sdk.Client(api_key=key)
