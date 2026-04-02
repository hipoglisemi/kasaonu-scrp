import os
from sqlalchemy import create_engine
from src.models import Base
from dotenv import load_dotenv

load_dotenv()

def create_tables():
    engine = create_engine(os.getenv('DATABASE_URL'))
    print(f"Connecting to database to ensure point_blank_rules exists...")
    Base.metadata.create_all(engine, tables=[Base.metadata.tables['point_blank_rules']])
    print("✅ Table point_blank_rules created/verified.")

if __name__ == "__main__":
    create_tables()
