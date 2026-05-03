import sys
from src.database import get_db_session
from src.models import Campaign

cid = int(sys.argv[1]) if len(sys.argv) > 1 else 17989

with get_db_session() as db:
    c = db.query(Campaign).get(cid)
    if c:
        print(f"ID: {c.id}")
        print(f"Title: {c.title}")
        print(f"Cards: {c.eligible_cards}")
        brands = [b.brand.name for b in c.brands]
        print(f"Brands: {', '.join(brands)}")
        print(f"Sector: {c.sector_slug}")
        print("-" * 20)
    else:
        print(f"ID {cid} not found")
