import psycopg2

DATABASE_URL = "postgres://postgres:OKaNWkuA52DaZoaTsGm6gCCqTgk03W9PXsFIWsc77NhTAGwZID3wqOel58mkOsBB@localhost:5434/postgres"

try:
    conn = psycopg2.connect(DATABASE_URL)
    cur = conn.cursor()
    cur.execute("SELECT clean_text FROM campaigns WHERE is_active = TRUE AND clean_text IS NOT NULL LIMIT 500")
    rows = cur.fetchall()
    
    total_chars = 0
    total_tokens = 0
    for r in rows:
        text = r[0] or ""
        total_chars += len(text)
        total_tokens += len(text) / 4.0
        
    avg_tokens = total_tokens / len(rows) if rows else 0
    print(f"Sampled {len(rows)} campaigns.")
    print(f"Average tokens per campaign: {avg_tokens:.2f}")
    
    est_total_input = (avg_tokens + 200) * 2000
    est_output_tokens = 50 * 2000
    
    cost_input = (est_total_input / 1_000_000) * 0.15
    cost_output = (est_output_tokens / 1_000_000) * 0.60
    
    print(f"Estimated Cost per 2000 camps scan: ${cost_input + cost_output:.4f}")
    
    cur.close()
    conn.close()
except Exception as e:
    print(e)
