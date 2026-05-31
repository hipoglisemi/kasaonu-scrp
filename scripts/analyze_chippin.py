import psycopg2
from psycopg2.extras import RealDictCursor

DATABASE_URL = "postgres://postgres:OKaNWkuA52DaZoaTsGm6gCCqTgk03W9PXsFIWsc77NhTAGwZID3wqOel58mkOsBB@localhost:5434/postgres"

def analyze_chippin_duplicates():
    conn = psycopg2.connect(DATABASE_URL)
    cur = conn.cursor(cursor_factory=RealDictCursor)
    
    print("🔍 Analyzing duplicate Chippin campaigns in database...")
    print("==========================================================================")
    
    cur.execute("""
        SELECT 
            c.id, 
            c.title, 
            c.slug,
            c.tracking_url as trackingUrl, 
            c.is_active as isActive,
            c.is_approved as isApproved,
            c.date_extended as dateExtended,
            c.start_date as startDate,
            c.end_date as endDate,
            c.created_at as createdAt,
            c.updated_at as updatedAt,
            card.name as cardName,
            bank.name as bankName
        FROM campaigns c
        LEFT JOIN cards card ON card.id = c.card_id
        LEFT JOIN banks bank ON bank.id = card.bank_id
        WHERE c.title ILIKE '%Europcar%' OR c.title ILIKE '%Bilet.com%'
        ORDER BY c.title, c.created_at DESC
    """)
    
    rows = cur.fetchall()
    print(f"📊 Found {len(rows)} matching campaigns:")
    print("--------------------------------------------------------------------------")
    
    for r in rows:
        print(f"ID: #{r['id']}")
        print(f"  Title: {r['title']}")
        print(f"  Slug: {r['slug']}")
        print(f"  Card/Bank: {r['cardname']} ({r['bankname']})")
        print(f"  URL: {r['trackingurl']}")
        print(f"  Status: isActive={r['isactive']} | isApproved={r['isapproved']} | dateExtended={r['dateextended']}")
        print(f"  Dates: {r['startdate']} -> {r['enddate']}")
        print(f"  Created: {r['createdat']} | Updated: {r['updatedat']}")
        print("-" * 74)
        
    cur.close()
    conn.close()

if __name__ == "__main__":
    analyze_chippin_duplicates()
