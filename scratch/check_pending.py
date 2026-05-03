from src.database import get_db_session
from src.models import Campaign

with get_db_session() as db:
    ids = [18115, 18116, 18117, 18118, 18119]
    for cid in ids:
        c = db.query(Campaign).get(cid)
        if c:
            print(f"ID: {c.id}, Approved: {c.is_approved}, Active: {c.is_active}, Title: {c.title}")
        else:
            print(f"ID: {cid} Not found")
