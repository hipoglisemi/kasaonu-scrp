import os
import psycopg2
from dotenv import load_dotenv

load_dotenv()
conn = psycopg2.connect(os.getenv('DATABASE_URL'))
cur = conn.cursor()
cur.execute("""
    SELECT 
        b.name, 
        COUNT(c.id) 
    FROM campaigns c 
    JOIN master_banks b ON c.bank_id = b.id 
    WHERE c.is_active = true 
    AND c.is_approved = false 
    GROUP BY b.name 
    ORDER BY count DESC;
""")
for row in cur.fetchall():
    print(f"{row[0]}: {row[1]}")
