import psycopg2

DATABASE_URL = "postgres://postgres:OKaNWkuA52DaZoaTsGm6gCCqTgk03W9PXsFIWsc77NhTAGwZID3wqOel58mkOsBB@localhost:5434/postgres"
conn = psycopg2.connect(DATABASE_URL)
cur = conn.cursor()
cur.execute("DELETE FROM test_campaigns WHERE slug = 'milessmiles6tl1mil';")
cur.execute("DELETE FROM campaigns WHERE slug = 'milessmiles6tl1mil';")
conn.commit()
print("Deleted test campaign for clean test run.")
cur.close()
conn.close()
