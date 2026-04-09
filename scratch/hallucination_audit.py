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

ids_path = "scripts/repair_ids.txt"
target_ids = []
if os.path.exists(ids_path):
    with open(ids_path, "r") as f:
        target_ids = [int(line.strip()) for line in f if line.strip().isdigit()]

# Kullanıcının "bunlar doğru" dediği ID'leri çıkaralım
exclude_ids = [11206, 14734, 15723]
target_ids = [tid for tid in target_ids if tid not in exclude_ids]

query = text("""
SELECT 
    c.id, 
    c.title, 
    c.description,
    s.name as sector_name, 
    string_agg(b.name, '|') as brands
FROM campaigns c
JOIN sectors s ON c.sector_id = s.id 
LEFT JOIN campaign_brands cb ON c.id = cb.campaign_id
LEFT JOIN brands b ON cb.brand_id = b.id
WHERE c.id IN :id_list
GROUP BY c.id, c.title, c.description, s.name;
""")

with engine.connect() as conn:
    result = conn.execute(query, {"id_list": tuple(target_ids)})
    
    print("\n--- 🔍 DEEP ANALYSIS OF IRRELEVANT MATCHES ---")
    
    for row in result:
        brands = row.brands.split('|') if row.brands else []
        if not brands: continue
        
        # Alakasızlık kontrolü: Başlıkta geçmeyip metinde "olumsuz" geçiyor mu?
        suspicious_brands = []
        for b in brands:
            if b.lower() not in row.title.lower():
                # Başlıkta yoksa metne bakalım
                desc_lower = row.description.lower() if row.description else ""
                # "hariç", "geçerli değil", "kapsamaz" gibi kelimelerin yakınında mı?
                context_indices = [desc_lower.find(b.lower())]
                for idx in context_indices:
                    if idx != -1:
                        context = desc_lower[max(0, idx-40):min(len(desc_lower), idx+40)]
                        if any(neg in context for neg in ["hariç", "geçerli değil", "değildir", "kapsamaz", "başka"]):
                            suspicious_brands.append(f"{b} (Context: ...{context}...)")

        if suspicious_brands or len(brands) > 5: # Çok fazla marka da hala şüpheli
            print(f"ID: {row.id} | Sector: {row.sector_name}")
            print(f"Title: {row.title}")
            print(f"All Brands: {', '.join(brands)}")
            if suspicious_brands:
                print(f"🚩 FLAG: Found Negative Context for: {', '.join(suspicious_brands)}")
            print("-" * 50)

    print("--- ANALYSIS COMPLETE ---")
