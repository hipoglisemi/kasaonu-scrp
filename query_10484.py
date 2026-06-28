import psycopg2

DATABASE_URL = "postgres://postgres:OKaNWkuA52DaZoaTsGm6gCCqTgk03W9PXsFIWsc77NhTAGwZID3wqOel58mkOsBB@localhost:5434/postgres"

conn = psycopg2.connect(DATABASE_URL)
cur = conn.cursor()
cur.execute("SELECT url FROM campaigns WHERE id = 10484")
res = cur.fetchone()
print(f"URL: {res[0] if res else 'Not found'}")
conn.close()
