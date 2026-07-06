import os
from dotenv import load_dotenv
import pandas as pd
from sqlalchemy import create_engine, text

load_dotenv()

DATABASE_URL = os.environ.get("DATABASE_URL")
if DATABASE_URL and DATABASE_URL.startswith("postgres://"):
    DATABASE_URL = DATABASE_URL.replace("postgres://", "postgresql://", 1)

engine = create_engine(DATABASE_URL)

from sqlalchemy import inspect

with engine.begin() as conn:
    query = text("""
        UPDATE campaigns c
        SET is_approved = True, is_active = True
        FROM cards crd, banks b
        WHERE c.card_id = crd.id AND crd.bank_id = b.id
        AND c.is_approved = False
        AND (b.name ILIKE '%yapı kredi%' OR b.name ILIKE '%yapıkredi%' OR crd.name ILIKE '%world%' OR crd.name ILIKE '%adios%' OR crd.name ILIKE '%crystal%')
    """)
    result = conn.execute(query)
    print(f'Updated {result.rowcount} pending YapıKredi/World/Adios/Crystal campaigns to Approved & Active.')
