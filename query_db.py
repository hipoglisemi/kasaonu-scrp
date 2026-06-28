import psycopg2

DATABASE_URL = "postgres://postgres:OKaNWkuA52DaZoaTsGm6gCCqTgk03W9PXsFIWsc77NhTAGwZID3wqOel58mkOsBB@localhost:5434/postgres"
try:
    conn = psycopg2.connect(DATABASE_URL)
    cur = conn.cursor()
    cur.execute("SELECT id, end_date, conditions FROM campaigns WHERE id IN (10484, 15973)")
    rows = cur.fetchall()
    for r in rows:
        print(f"ID: {r[0]} | End Date: {r[1]}")
        print(f"Conditions: {r[2][:150]}...")
        print("-" * 40)
except Exception as e:
    print(e)
