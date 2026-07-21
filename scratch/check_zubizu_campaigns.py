import sys
import os

project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if project_root not in sys.path:
    sys.path.insert(0, project_root)

from src.database import get_db_session
from src.models import Campaign, CampaignBrand, Brand, Sector, Card

with get_db_session() as db:
    card = db.query(Card).filter(Card.slug == 'zubizu').first()
    campaigns = db.query(Campaign).filter(
        Campaign.card_id == card.id,
        Campaign.is_approved == False
    ).limit(5).all()

    for c in campaigns:
        sector_name = c.sector.name if c.sector else "None"
        brands = [cb.brand.name for cb in db.query(CampaignBrand).filter(CampaignBrand.campaign_id == c.id).all()]
        print(f"\nTitle: {c.title}")
        print(f"Sector: {sector_name}")
        print(f"Brands: {brands}")
