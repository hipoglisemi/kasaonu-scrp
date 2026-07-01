from src.database import get_db_session
from sqlalchemy import text

with get_db_session() as db:
    total = db.execute(text("SELECT COUNT(*) FROM campaigns WHERE is_active = true")).scalar()
    with_blurhash = db.execute(text("SELECT COUNT(*) FROM campaigns WHERE is_active = true AND blurhash IS NOT NULL AND blurhash != ''")).scalar()
    print(f"Total active campaigns: {total}")
    print(f"Active campaigns WITH blurhash: {with_blurhash}")
    print(f"Active campaigns WITHOUT blurhash: {total - with_blurhash}")
