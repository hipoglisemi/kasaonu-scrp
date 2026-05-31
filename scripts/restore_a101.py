import psycopg2

DATABASE_URL = "postgres://postgres:OKaNWkuA52DaZoaTsGm6gCCqTgk03W9PXsFIWsc77NhTAGwZID3wqOel58mkOsBB@localhost:5434/postgres"

def restore_a101():
    conn = psycopg2.connect(DATABASE_URL)
    cur = conn.cursor()
    
    campaign_id = 14803
    correct_url = "https://www.paraf.com.tr/content/parafcard/tr/kampanyalar/market/a101de-pesin-fiyatina-6-aya-varan-taksit.html"
    correct_slug = "halkbank-paraf-a101de-pesin-fiyatina-6-aya-varan-taksit"
    
    print(f"🔄 Restoring Campaign ID #{campaign_id} to its original Paraf URL and slug...")
    
    cur.execute("""
        UPDATE campaigns 
        SET tracking_url = %s, 
            slug = %s,
            is_approved = true,
            date_extended = true
        WHERE id = %s
    """, (correct_url, correct_slug, campaign_id))
    
    print(f"✅ Successfully restored {cur.rowcount} rows!")
    conn.commit()
    cur.close()
    conn.close()

if __name__ == "__main__":
    restore_a101()
