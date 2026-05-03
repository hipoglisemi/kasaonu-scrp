from src.database import get_db_session
from src.models import Campaign

with get_db_session() as db:
    ids = [18106, 17961, 17962, 17967, 17968, 17970, 17973, 17975, 17979, 17890]
    for cid in ids:
        c = db.query(Campaign).get(cid)
        if c:
            print(f"ID: {c.id} | Cards: {c.eligible_cards}")
        else:
            print(f"ID: {cid} | Not found/repaired yet")
