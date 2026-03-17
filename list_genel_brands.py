import os
import psycopg2
from dotenv import load_dotenv

# .env dosyasını yükle
load_dotenv()

def run_query():
    db_url = os.getenv("DATABASE_URL")
    if not db_url:
        print("DATABASE_URL not found in .env")
        return

    try:
        conn = psycopg2.connect(db_url)
        cur = conn.cursor()
        
        query = """
        SELECT id, name, slug, is_active 
        FROM brands 
        WHERE slug LIKE '%genel%' 
        OR name LIKE '%Genel%';
        """
        
        cur.execute(query)
        rows = cur.fetchall()
        
        if not rows:
            print("No matching brands found.")
        else:
            print(f"{'ID':<40} | {'Name':<20} | {'Slug':<20} | {'Active'}")
            print("-" * 100)
            for row in rows:
                print(f"{row[0]:<40} | {row[1]:<20} | {row[2]:<20} | {row[3]}")
                
        cur.close()
        conn.close()
    except Exception as e:
        print(f"Error executing query: {e}")

if __name__ == "__main__":
    run_query()
