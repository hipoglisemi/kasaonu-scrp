import psycopg2

DATABASE_URL = "postgres://postgres:OKaNWkuA52DaZoaTsGm6gCCqTgk03W9PXsFIWsc77NhTAGwZID3wqOel58mkOsBB@localhost:5434/postgres"
conn = psycopg2.connect(DATABASE_URL)
cur = conn.cursor()

# Get the Card ID for 'tkpay-cuzdan'
cur.execute("SELECT id FROM cards WHERE slug = 'tkpay-cuzdan'")
card_row = cur.fetchone()
if card_row:
    card_id = card_row[0]
    print(f"Deleting campaigns for card_id: {card_id}")
    
    # Delete from campaign_brands
    cur.execute("""
        DELETE FROM campaign_brands 
        WHERE campaign_id IN (SELECT id FROM campaigns WHERE card_id = %s)
           OR campaign_id IN (SELECT id FROM test_campaigns WHERE card_id = %s)
    """, (card_id, card_id))
    
    # Delete from campaigns
    cur.execute("DELETE FROM campaigns WHERE card_id = %s", (card_id,))
    
    # Delete from test_campaigns
    cur.execute("DELETE FROM test_campaigns WHERE card_id = %s", (card_id,))
    
    conn.commit()
    print("Successfully deleted all campaigns for 'tkpay-cuzdan' from both campaigns and test_campaigns tables.")
else:
    print("Card 'tkpay-cuzdan' not found.")

cur.close()
conn.close()
