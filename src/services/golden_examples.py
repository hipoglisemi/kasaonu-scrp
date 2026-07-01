from datetime import datetime, timedelta
import time
import difflib

# ---------------------------------------------------------------------------
# 1) CACHE KATMANI
# ---------------------------------------------------------------------------
_CACHE = {}
_CACHE_TTL_SECONDS = 60 * 60 * 12

def _cache_get(key):
    entry = _CACHE.get(key)
    if not entry:
        return None
    value, ts = entry
    if time.time() - ts > _CACHE_TTL_SECONDS:
        return None
    return value

def _cache_set(key, value):
    _CACHE[key] = (value, time.time())

# ---------------------------------------------------------------------------
# 2) GOLDEN EXAMPLES ÇEKME
# ---------------------------------------------------------------------------
def _get_golden_examples_for_bank(db, bank_name, limit=3, recency_days=14, min_quality_score=95):
    from src.models import Campaign, Card, Bank
    
    cache_key = f"golden:{bank_name}"
    cached = _cache_get(cache_key)
    if cached is not None:
        return cached

    cutoff = datetime.utcnow() - timedelta(days=recency_days)

    query = (
        db.query(Campaign)
        .join(Card, Campaign.card_id == Card.id)
        .join(Bank, Card.bank_id == Bank.id)
        .filter(Bank.name == bank_name)
        .filter(Campaign.is_approved == True)
        .filter(Campaign.cards_audited_at.isnot(None))
        .filter(Campaign.quality_score >= min_quality_score)
        .filter(Campaign.cards_audited_at >= cutoff)
    )

    results = query.order_by(Campaign.cards_audited_at.desc()).limit(limit).all()

    if len(results) < limit:
        query_fallback = (
            db.query(Campaign)
            .join(Card, Campaign.card_id == Card.id)
            .join(Bank, Card.bank_id == Bank.id)
            .filter(Bank.name == bank_name)
            .filter(Campaign.is_approved == True)
            .filter(Campaign.cards_audited_at.isnot(None))
            .filter(Campaign.quality_score >= min_quality_score)
        )
        results = query_fallback.order_by(Campaign.cards_audited_at.desc()).limit(limit).all()

    examples = []
    for c in results:
        examples.append({
            "title": c.title,
            "ai_marketing_text": c.ai_marketing_text or c.description or "",
            "conditions": c.conditions or "",
            "participation": c.participation or ""
        })

    _cache_set(cache_key, examples)
    return examples

# ---------------------------------------------------------------------------
# 3) "KAÇINILMASI GEREKEN HATALAR" NOTU
# ---------------------------------------------------------------------------
def _get_recent_correction_warnings(db, bank_name, limit=5, recency_days=14):
    # original_text kolonumuz yok. Bunun yerine DB'de manuel duzeltme yapildigina dair log yok.
    # Bu adimi su anlik bos liste dondurecek sekilde birakiyoruz, ileride original_text veya audit_log 
    # eklendiginde aktif edilebilir.
    return []

# ---------------------------------------------------------------------------
# 4) PROMPT'A ENJEKTE EDİLECEK METNİ OLUŞTURMA
# ---------------------------------------------------------------------------
def build_few_shot_block(db, bank_name):
    examples = _get_golden_examples_for_bank(db, bank_name)
    warnings = _get_recent_correction_warnings(db, bank_name)

    if not examples and not warnings:
        return ""

    parts = []

    if examples:
        parts.append(
            "\n💡 DİKKAT! Aşağıda bu banka için sistem yöneticisi (admin) "
            "tarafından daha önce onaylanmış 'altın standart' örnek kampanyalar var. Üreteceğin "
            "içeriğin tonunu, üslubunu ve format yapısını mutlaka bu örneklere "
            "benzet (Kelimesi kelimesine kopyalama, sadece stil ve ton referansı al):\n"
        )
        for i, ex in enumerate(examples, 1):
            cond_lines = [c.strip() for c in ex['conditions'].split('\n') if c.strip()][:3]
            cond_preview = "\n- ".join(cond_lines) if cond_lines else ""
            
            parts.append(
                f"[Örnek {i}]\n"
                f"Başlık: {ex['title']}\n"
                f"Pazarlama Metni: {ex['ai_marketing_text'][:300]}\n"
                f"Katılım: {ex['participation']}\n"
                f"Şartlar (İlk 3 Madde): \n- {cond_preview}\n"
            )

    if warnings:
        parts.append(
            "\n⚠️ GEÇMİŞTE YAPILAN HATALAR — BUNLARI TEKRARLAMA:\n"
        )
        for w in warnings:
            parts.append(f"- {w}")

    return "\n".join(parts)
