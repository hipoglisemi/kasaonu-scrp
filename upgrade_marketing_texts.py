"""
upgrade_marketing_texts.py
===========================
Finds ALL campaigns with missing or emoji-free ai_marketing_text and
regenerates them using Gemini AI with the correct emojified format.

Usage:
    python3 upgrade_marketing_texts.py              # dry-run, shows what would change
    python3 upgrade_marketing_texts.py --execute    # apply changes
    python3 upgrade_marketing_texts.py --execute --limit 50   # process max 50
    python3 upgrade_marketing_texts.py --execute --ids 17081,17076  # specific IDs
"""

import os
import sys
import re
import argparse
import time
import logging
from datetime import datetime
from typing import Optional
from dotenv import load_dotenv

sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from src.database import get_db_session
from src.models import Campaign, Card, Bank
from src.utils.gemini_client import generate_with_rotation
from sqlalchemy import or_
from sqlalchemy.orm import joinedload

load_dotenv()

logging.basicConfig(level=logging.INFO, format="%(message)s")
logger = logging.getLogger("MarketingUpgrader")

MODEL = "gemma-4-31b-it"

MARKETING_PROMPT = """\
Sen uzman bir pazarlama metni yazarısın. Aşağıdaki kampanya bilgilerini kullanarak \
kullanıcıyı heyecanlandıracak, enerjik ve samimi bir "Pazarlama Özeti" oluştur.

KAMPANYA BİLGİLERİ:
Başlık: {title}
Banka/Kart: {bank}
Açıklama: {description}

KURALLAR:
1. **DİL**: Tamamı TÜRKÇE.
2. **TARZ**: Enerjik, samimi, kullanıcıyı teşvik edici.
3. **EMOJİ (ZORUNLU)**: Her cümlenin sonuna veya arasına uygun emoji koy \
(🎉 🚀 💳 🛒 ⛽ ✈️ 🍕 💰 🎁 🏷️ gibi kampanya konusuyla ilgili).
4. **UZUNLUK**: 2-3 cümle, en az 120 karakter, en fazla 280 karakter.
5. **SOMUT DEĞERLER**: Başlıktaki rakamları (TL, %, taksit) mutlaka belirt.
6. **YASAK**: Teknik katılım detaylarına girme, sadece avantajı anlat. \
"Banka üyelerine" gibi jenerik ifadeler kullanma.

ÖRNEK ÇIKTI:
"İstikbal'de mobilya alışverişinizi Bankkart'la 5 taksitle ödeyin! 🛋️ \
Evinizi yenilerken bütçenizi zorlamayan bu özel fırsatı kaçırmayın! 💳🎉"

Sadece pazarlama metnini yaz, tırnak işareti veya başka açıklama EKLEME.
"""

EMOJI_RE = re.compile(
    "["
    "\U0001F300-\U0001F9FF"
    "\U00002702-\U000027B0"
    "\U0000FE00-\U0000FE0F"
    "\U00002500-\U00002BEF"
    "\U0001F1E0-\U0001F1FF"
    "\U0001F004-\U0001F0CF"
    "\U0001F600-\U0001F64F"
    "\U0001F680-\U0001F6FF"
    "\U0001F700-\U0001F77F"
    "]+",
    flags=re.UNICODE,
)


def has_emoji(text: str) -> bool:
    return bool(EMOJI_RE.search(text or ""))


def find_target_campaigns(db, ids=None):
    """Return campaigns with empty OR emoji-free ai_marketing_text."""
    if ids:
        return db.query(Campaign).options(joinedload(Campaign.card).joinedload(Card.bank))\
            .filter(Campaign.id.in_(ids)).all()

    all_with_text = db.query(Campaign).options(
        joinedload(Campaign.card).joinedload(Card.bank)
    ).filter(
        Campaign.ai_marketing_text != None,
        Campaign.ai_marketing_text != ""
    ).all()

    no_emoji = [c for c in all_with_text if not has_emoji(c.ai_marketing_text or "")]

    empty = db.query(Campaign).options(
        joinedload(Campaign.card).joinedload(Card.bank)
    ).filter(
        or_(Campaign.ai_marketing_text == None, Campaign.ai_marketing_text == "")
    ).all()

    # Deduplicate
    seen = set()
    result = []
    for c in no_emoji + empty:
        if c.id not in seen:
            seen.add(c.id)
            result.append(c)
    return result


def generate_marketing_text(campaign: Campaign) -> Optional[str]:
    bank_name = ""
    try:
        bank_name = campaign.card.bank.name if campaign.card and campaign.card.bank else ""
    except Exception:
        pass

    prompt = MARKETING_PROMPT.format(
        title=campaign.title or "",
        bank=bank_name,
        description=campaign.description or campaign.title or "",
    )

    try:
        result = generate_with_rotation(prompt, model=MODEL)
        if result:
            # Strip surrounding quotes if AI added them
            result = result.strip().strip('"').strip("'").strip()
        return result if result else None
    except Exception as e:
        logger.error(f"   ❌ Gemini error: {e}")
        return None


def main():
    parser = argparse.ArgumentParser(description="Upgrade emoji-free ai_marketing_text fields")
    parser.add_argument("--execute", action="store_true", help="Apply changes (default: dry-run)")
    parser.add_argument("--limit", type=int, default=0, help="Max campaigns to process (0 = all)")
    parser.add_argument("--ids", type=str, default="", help="Comma-separated campaign IDs to target")
    args = parser.parse_args()

    dry_run = not args.execute
    target_ids = [int(x.strip()) for x in args.ids.split(",") if x.strip()] if args.ids else None

    logger.info("=" * 60)
    logger.info(f"🚀 AI Marketing Text Upgrader")
    logger.info(f"   Mode: {'DRY RUN (no changes)' if dry_run else '🔥 EXECUTE (will update DB)'}")
    logger.info(f"   Model: {MODEL}")
    if target_ids:
        logger.info(f"   Target IDs: {target_ids}")
    if args.limit:
        logger.info(f"   Limit: {args.limit}")
    logger.info("=" * 60)

    with get_db_session() as db:
        campaigns = find_target_campaigns(db, ids=target_ids)

        if args.limit:
            campaigns = campaigns[: args.limit]

        total = len(campaigns)
        logger.info(f"🔍 Found {total} campaigns to upgrade.\n")

        if total == 0:
            logger.info("✅ Nothing to do!")
            return

        updated = 0
        failed = 0

        for i, campaign in enumerate(campaigns, 1):
            bank_name = ""
            try:
                bank_name = campaign.card.bank.name if campaign.card and campaign.card.bank else "?"
            except Exception:
                pass

            old_text = (campaign.ai_marketing_text or "")[:80]
            logger.info(f"[{i}/{total}] ID {campaign.id} — {campaign.title[:45]}")
            logger.info(f"   Bank: {bank_name}")
            logger.info(f"   OLD: {repr(old_text)}")

            if dry_run:
                logger.info("   → DRY RUN: would generate new text")
                continue

            new_text = generate_marketing_text(campaign)
            if new_text and has_emoji(new_text):
                campaign.ai_marketing_text = new_text
                campaign.updated_at = datetime.utcnow()
                updated += 1
                logger.info(f"   ✅ NEW: {new_text[:80]}...")
            elif new_text:
                # AI returned text but forgot emojis — log and skip (don't degrade)
                logger.warning(f"   ⚠️  AI returned emoji-free text, skipping: {new_text[:60]}")
                failed += 1
            else:
                logger.warning(f"   ⚠️  Empty AI response, skipping.")
                failed += 1

            time.sleep(1.5)  # Rate limit guard

        if not dry_run:
            db.commit()
            logger.info("\n" + "=" * 60)
            logger.info(f"🏁 Done! Updated: {updated} | Failed/Skipped: {failed}")
        else:
            logger.info(f"\n🧪 Dry run complete. {total} campaigns would be processed.")
            logger.info("   Run with --execute to apply changes.")


if __name__ == "__main__":
    main()
