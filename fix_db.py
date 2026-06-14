import psycopg2
import os

DATABASE_URL = "postgres://postgres:OKaNWkuA52DaZoaTsGm6gCCqTgk03W9PXsFIWsc77NhTAGwZID3wqOel58mkOsBB@localhost:5434/postgres"

conn = psycopg2.connect(DATABASE_URL)
cur = conn.cursor()
cur.execute('ALTER TABLE "test_campaigns" ADD COLUMN IF NOT EXISTS "cards_audited_at" TIMESTAMP;')
conn.commit()
print("Added cards_audited_at to test_campaigns")
cur.close()
conn.close()
