"""
AI Parser Service - REDIRECT LAYER
===================================
Bu dosya artık sadece bir yönlendirme katmanıdır.
Tüm iş mantığı ai_parser_golden.py'de merkezileştirilmiştir.

Eski sistem yedek olarak ai_parser_legacy_backup.py'de saklanmaktadır.

Scraperlar bu dosyadan şunları import eder:
  - AIParser (class)              → 27 scraper kullanıyor
  - parse_api_campaign (function) → 15 scraper kullanıyor
  - get_ai_parser (function)      → dahili kullanım
  - parse_campaign (function)     → dahili kullanım
  - BANK_RULES (dict)             → eski uyumluluk
"""
from src.services.ai_parser_golden import (  # type: ignore
    AIParserGolden,
    get_golden_parser,
    parse_api_campaign,
    BANK_CARD_KEYWORDS,
)

from typing import Dict, Any, Optional

# ── BANK_RULES compat (eski referanslar için) ────────────────────────
# Eski BANK_RULES artık Golden Parser'da BANK_CARD_KEYWORDS olarak yaşıyor.
# Hiçbir scraper bunu doğrudan import etmez ama güvenlik için tutuyoruz.
BANK_RULES = {}

# ── AIParser compat class ────────────────────────────────────────────
# 27 scraper bu sınıfı `AIParser()` olarak oluşturup
# `.parse_campaign_data(...)` çağırıyor.
# Artık doğrudan AIParserGolden'a yönlendiriyoruz.

class AIParser(AIParserGolden):
    """
    Backward-compatible AIParser.
    Scraperlar `AIParser()` deyip `parse_campaign_data()` çağırabilir.
    Tüm iş mantığı AIParserGolden'da.
    """
    def __init__(self, model_name: Optional[str] = None):
        from src.services.ai_parser_golden import _create_default_client  # type: ignore
        client = _create_default_client()
        super().__init__(model_client=client)
        print(f"[DEBUG] AIParser → Golden Parser V3 initialized.")


# ── Standalone function compat ───────────────────────────────────────

_parser_instance = None

def get_ai_parser() -> AIParser:
    """Get singleton AI parser instance."""
    global _parser_instance
    if _parser_instance is None:
        _parser_instance = AIParser()
    return _parser_instance


def parse_campaign(
    raw_text: str,
    title: Optional[str] = None,
    bank_name: Optional[str] = None,
    card_name: Optional[str] = None,
    tracking_url: Optional[str] = None,
    force: bool = False,
    campaign_id: Optional[int] = None,
    og_title: Optional[str] = None
) -> Dict:
    """Main entry point for AI parsing."""
    parser = get_ai_parser()
    return parser.parse_campaign_data(raw_text, title, bank_name, card_name, tracking_url, force, campaign_id, og_title=og_title)


# parse_api_campaign is already imported from ai_parser_golden at module level
