import os
import psycopg2

DATABASE_URL = "postgres://postgres:OKaNWkuA52DaZoaTsGm6gCCqTgk03W9PXsFIWsc77NhTAGwZID3wqOel58mkOsBB@localhost:5434/postgres"

try:
    conn = psycopg2.connect(DATABASE_URL)
    cur = conn.cursor()
    
    # 1. Update the three campaigns
    query = """
        UPDATE campaigns 
        SET 
            end_date = '2026-06-30'::date,
            date_extended = FALSE,
            updated_at = NOW()
        WHERE id IN (10484, 15973, 14921)
        RETURNING id, title, end_date;
    """
    cur.execute(query)
    rows = cur.fetchall()
    
    conn.commit()
    
    print("Reverted campaigns:")
    for r in rows:
        print(f"ID: {r[0]} | End Date: {r[2]} | Title: {r[1]}")
        
    cur.close()
    conn.close()
except Exception as e:
    print(f"Error: {e}")
