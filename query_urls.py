import psycopg2

DATABASE_URL = "postgres://postgres:OKaNWkuA52DaZoaTsGm6gCCqTgk03W9PXsFIWsc77NhTAGwZID3wqOel58mkOsBB@localhost:5434/postgres"
try:
    conn = psycopg2.connect(DATABASE_URL)
    cur = conn.cursor()
    cur.execute("SELECT id, tracking_url FROM campaigns WHERE id IN (14921, 15973, 10484)")
    rows = cur.fetchall()
    for r in rows:
        print(f"ID: {r[0]} URL: {r[1]}")
except Exception as e:
    print(e)
