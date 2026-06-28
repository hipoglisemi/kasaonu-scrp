import psycopg2

DATABASE_URL = "postgres://postgres:OKaNWkuA52DaZoaTsGm6gCCqTgk03W9PXsFIWsc77NhTAGwZID3wqOel58mkOsBB@localhost:5434/postgres"

try:
    conn = psycopg2.connect(DATABASE_URL)
    cur = conn.cursor()
    
    # Check how many campaigns were added in the last 30 days
    cur.execute("SELECT COUNT(*) FROM campaigns WHERE created_at >= NOW() - INTERVAL '30 days'")
    new_campaigns = cur.fetchone()[0]
    
    # Check total active campaigns
    cur.execute("SELECT COUNT(*) FROM campaigns WHERE is_active = TRUE")
    total_active = cur.fetchone()[0]
    
    print(f"New campaigns in last 30 days: {new_campaigns}")
    print(f"Total active campaigns: {total_active}")
    
    cur.close()
    conn.close()
except Exception as e:
    print(e)
