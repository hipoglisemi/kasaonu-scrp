import sys
import os

project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if project_root not in sys.path:
    sys.path.insert(0, project_root)

from src.database import get_db_session
from src.models import Campaign, CampaignBrand, Card

with get_db_session() as db:
    card = db.query(Card).filter(Card.slug == 'zubizu').first()
    campaigns = db.query(Campaign).filter(
        Campaign.card_id == card.id,
        Campaign.is_approved == False
    ).all()

    count = len(campaigns)
    for c in campaigns:
        # CampaignBrand records are usually cascaded or we delete them manually
        db.query(CampaignBrand).filter(CampaignBrand.campaign_id == c.id).delete()
        db.delete(c)
    
    db.commit()
    print(f"Successfully deleted {count} unapproved Zubizu campaigns so they can be re-scraped cleanly.")
