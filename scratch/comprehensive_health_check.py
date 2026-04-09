import os
from sqlalchemy import create_engine, text
from dotenv import load_dotenv

load_dotenv()

DATABASE_URL = os.getenv("DATABASE_URL")
if not DATABASE_URL:
    print("❌ DATABASE_URL not found!")
    exit(1)

if DATABASE_URL.startswith("postgres://"):
    DATABASE_URL = DATABASE_URL.replace("postgres://", "postgresql://", 1)

engine = create_engine(DATABASE_URL)

# repair_ids.txt dosyasındaki ID'leri oku
ids_path = "scripts/repair_ids.txt"
target_ids = []
if os.path.exists(ids_path):
    with open(ids_path, "r") as f:
        target_ids = [int(line.strip()) for line in f if line.strip().isdigit()]

if not target_ids:
    print("❌ No target IDs found in scripts/repair_ids.txt")
    exit(1)

query = text("""
SELECT 
    c.id, 
    c.title, 
    s.name as sector_name, 
    s.slug as sector_slug,
    COUNT(b.id) as brand_count,
    string_agg(b.name, ', ') as brands
FROM campaigns c
JOIN sectors s ON c.sector_id = s.id 
LEFT JOIN campaign_brands cb ON c.id = cb.campaign_id
LEFT JOIN brands b ON cb.brand_id = b.id
WHERE c.id IN :id_list
GROUP BY c.id, c.title, s.name, s.slug;
""")

with engine.connect() as conn:
    result = conn.execute(query, {"id_list": tuple(target_ids)})
    
    print("\n--- 🚩 SUSPECT CAMPAIGNS (Potentially Wrong or Over-Branded) ---")
    print(f"{'ID':<6} {'Sector':<20} {'Br#':<4} {'Brands':<40} {'Title'}")
    print("-" * 120)
    
    clean_count = 0
    issue_count = 0
    
    for row in result:
        has_issue = False
        reason = ""
        
        # Criterion 1: Too many brands (Indicator of noise)
        if row.brand_count > 3:
            has_issue = True
            reason = "Too many brands"
            
        # Criterion 2: Sector mismatch (Sports brand in non-sports sector)
        sports_keywords = ["gs store", "fener", "beşiktaş", "kartal yuvası", "trabzon", "nike", "adidas"]
        if row.brands:
            brands_lower = row.brands.lower()
            if any(k in brands_lower for k in sports_keywords) and row.sector_slug != "kultur-sanat":
                has_issue = True
                reason = "Sports brand / Wrong sector"

        # Criterion 3: Other sector but has brand
        if row.sector_slug == "diger" and row.brand_count > 0:
            has_issue = True
            reason = "Sector is 'Other' but has brands"

        if has_issue:
            issue_count += 1
            print(f"{row.id:<6} {row.sector_name:<20} {row.brand_count:<4} {str(row.brands)[:40]:<40} {row.title[:40]}")
            print(f"      └─ ⚠️ ISSUE: {reason}")
        else:
            clean_count += 1
            
    print("-" * 120)
    print(f"📊 SUMMARY:")
    print(f"   ✅ Clean/Corrected: {clean_count}")
    print(f"   🚩 Still Suspect: {issue_count}")
    print(f"   📂 Total Checked: {clean_count + issue_count}")
    print("--- END CHECK ---\n")
