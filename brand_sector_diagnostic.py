import os
import json
import re
from sqlalchemy import create_engine, text
from dotenv import load_dotenv

load_dotenv()

# Point-Blank Matching Dictionary (V1 - Draft)
# Bu sözlük manuel olarak genişletilecek veya DB'den beslenecek.
MATCH_RULES = {
    # MARKET & GIDA
    "Migros": {"brand": "Migros", "sector": "Market & Gıda"},
    "Carrefoursa": {"brand": "Carrefoursa", "sector": "Market & Gıda"},
    "A101": {"brand": "A101", "sector": "Market & Gıda"},
    "Şok": {"brand": "Şok", "sector": "Market & Gıda"},
    "Bim": {"brand": "Bim", "sector": "Market & Gıda"},
    "Macrocenter": {"brand": "Macrocenter", "sector": "Market & Gıda"},
    "Getir": {"brand": "Getir", "sector": "E-Ticaret"},
    "İstegelsin": {"brand": "İstegelsin", "sector": "E-Ticaret"},
    
    # AKARYAKIT
    "Opet": {"brand": "Opet", "sector": "Akaryakıt"},
    "Shell": {"brand": "Shell", "sector": "Akaryakıt"},
    "Petrol Ofisi": {"brand": "Petrol Ofisi", "sector": "Akaryakıt"},
    "Bp": {"brand": "BP", "sector": "Akaryakıt"},
    "Aytemiz": {"brand": "Aytemiz", "sector": "Akaryakıt"},
    "TotalEnergies": {"brand": "TotalEnergies", "sector": "Akaryakıt"},
    "Total": {"brand": "TotalEnergies", "sector": "Akaryakıt"},
    "Lukoil": {"brand": "Lukoil", "sector": "Akaryakıt"},
    "Akaryakıt": {"brand": None, "sector": "Akaryakıt"},
    
    # E-TICARET
    "Trendyol": {"brand": "Trendyol", "sector": "E-Ticaret"},
    "Hepsiburada": {"brand": "Hepsiburada", "sector": "E-Ticaret"},
    "Amazon": {"brand": "Amazon", "sector": "E-Ticaret"},
    "n11": {"brand": "n11", "sector": "E-Ticaret"},
    "Pazarama": {"brand": "Pazarama", "sector": "E-Ticaret"},
    "Çiçeksepeti": {"brand": "Çiçeksepeti", "sector": "E-Ticaret"},
    "Modanisa": {"brand": "Modanisa", "sector": "E-Ticaret"},
    
    # ULASIM & TURIZM
    "Thy": {"brand": "Turkish Airlines", "sector": "Ulaşım"},
    "Pegasus": {"brand": "Pegasus", "sector": "Ulaşım"},
    "Ajet": {"brand": "Ajet", "sector": "Ulaşım"},
    "Enuygun": {"brand": "Enuygun", "sector": "Turizm & Konaklama"},
    "Etstur": {"brand": "Etstur", "sector": "Turizm & Konaklama"},
    "Jolly": {"brand": "Jolly Tur", "sector": "Turizm & Konaklama"},
    "Obilet": {"brand": "Obilet", "sector": "Ulaşım"},
    "Yolcu360": {"brand": "Yolcu360", "sector": "Ulaşım"},
    "Bitaksi": {"brand": "BiTaksi", "sector": "Ulaşım"},
    "Martı": {"brand": "Martı", "sector": "Ulaşım"},
    "Tureks": {"brand": "Tureks", "sector": "Ulaşım"},
    "Havalimanı": {"brand": None, "sector": "Ulaşım"},
    "Lounge": {"brand": None, "sector": "Ulaşım"},
    "Otopark": {"brand": None, "sector": "Ulaşım"},
    "Vale": {"brand": None, "sector": "Ulaşım"},
    "HGS": {"brand": None, "sector": "Ulaşım"},
    "Otoyol": {"brand": None, "sector": "Ulaşım"},
    "Köprü": {"brand": None, "sector": "Ulaşım"},
    "Yurt Dışı": {"brand": None, "sector": "Turizm & Konaklama"},
    "Ulaşım": {"brand": None, "sector": "Ulaşım"},
    "Turizm": {"brand": None, "sector": "Turizm & Konaklama"},
    "Otel": {"brand": None, "sector": "Turizm & Konaklama"},
    "Tatil": {"brand": None, "sector": "Turizm & Konaklama"},
    
    # DIJITAL & TELEKOM & FINANS
    "Netflix": {"brand": "Netflix", "sector": "Dijital Platform"},
    "Spotify": {"brand": "Spotify", "sector": "Dijital Platform"},
    "Youtube": {"brand": "YouTube", "sector": "Dijital Platform"},
    "Disney+": {"brand": "Disney+", "sector": "Dijital Platform"},
    "Exxen": {"brand": "Exxen", "sector": "Dijital Platform"},
    "Vodafone": {"brand": "Vodafone", "sector": "Fatura & Telekomünikasyon"},
    "Türk Telekom": {"brand": "Türk Telekom", "sector": "Fatura & Telekomünikasyon"},
    "Turkcell": {"brand": "Turkcell", "sector": "Fatura & Telekomünikasyon"},
    "idefix": {"brand": "idefix", "sector": "E-Ticaret"},
    "Paramkart": {"brand": "Param", "sector": "E-Ticaret"},
    "Param": {"brand": "Param", "sector": "E-Ticaret"},
    "PayTR": {"brand": "PayTR", "sector": "E-Ticaret"},
    "Hopi": {"brand": "Hopi", "sector": "E-Ticaret"},
    
    # GIYIM & MODA
    "Boyner": {"brand": "Boyner", "sector": "Giyim & Aksesuar"},
    "Zara": {"brand": "Zara", "sector": "Giyim & Aksesuar"},
    "Altınyıldız": {"brand": "Altınyıldız", "sector": "Giyim & Aksesuar"},
    "Beymen": {"brand": "Beymen", "sector": "Giyim & Aksesuar"},
    "LC Waikiki": {"brand": "LC Waikiki", "sector": "Giyim & Aksesuar"},
    "H&M": {"brand": "H&M", "sector": "Giyim & Aksesuar"},
    "Mavi": {"brand": "Mavi", "sector": "Giyim & Aksesuar"},
    "Koton": {"brand": "Koton", "sector": "Giyim & Aksesuar"},
    "DeFacto": {"brand": "DeFacto", "sector": "Giyim & Aksesuar"},
    "Flo": {"brand": "Flo", "sector": "Giyim & Aksesuar"},
    "Nike": {"brand": "Nike", "sector": "Giyim & Aksesuar"},
    "Adidas": {"brand": "Adidas", "sector": "Giyim & Aksesuar"},
    "Under Armour": {"brand": "Under Armour", "sector": "Giyim & Aksesuar"},
    "Kiğılı": {"brand": "Kiğılı", "sector": "Giyim & Aksesuar"},
    "Stradivarius": {"brand": "Stradivarius", "sector": "Giyim & Aksesuar"},
    "Yargıcı": {"brand": "Yargıcı", "sector": "Giyim & Aksesuar"},
    "Divarese": {"brand": "Divarese", "sector": "Giyim & Aksesuar"},
    "Ramsey": {"brand": "Ramsey", "sector": "Giyim & Aksesuar"},
    "KİP": {"brand": "KİP", "sector": "Giyim & Aksesuar"},
    "OXXO": {"brand": "OXXO", "sector": "Giyim & Aksesuar"},
    "Twist": {"brand": "Twist", "sector": "Giyim & Aksesuar"},
    "NetWork": {"brand": "NetWork", "sector": "Giyim & Aksesuar"},
    "Pierre Cardin": {"brand": "Pierre Cardin", "sector": "Giyim & Aksesuar"},
    "Ipekyol": {"brand": "Ipekyol", "sector": "Giyim & Aksesuar"},
    "Nocturne": {"brand": "Nocturne", "sector": "Giyim & Aksesuar"},
    "Sportive": {"brand": "Sportive", "sector": "Giyim & Aksesuar"},
    "Intersport": {"brand": "Intersport", "sector": "Giyim & Aksesuar"},
    "Samsonite": {"brand": "Samsonite", "sector": "Giyim & Aksesuar"},
    "Lumberjack": {"brand": "Lumberjack", "sector": "Giyim & Aksesuar"},
    "Brooks": {"brand": "Brooks", "sector": "Giyim & Aksesuar"},
    "Vakko": {"brand": "Vakko", "sector": "Giyim & Aksesuar"},
    "Penti": {"brand": "Penti", "sector": "Giyim & Aksesuar"},
    "Derimod": {"brand": "Derimod", "sector": "Giyim & Aksesuar"},
    "Desa": {"brand": "Desa", "sector": "Giyim & Aksesuar"},
    "Giyim": {"brand": None, "sector": "Giyim & Aksesuar"},
    "Ayakkabı": {"brand": None, "sector": "Giyim & Aksesuar"},
    
    # EV & MOBILYA
    "Ikea": {"brand": "IKEA", "sector": "Mobilya & Dekorasyon"},
    "Yataş": {"brand": "Yataş", "sector": "Mobilya & Dekorasyon"},
    "Vivense": {"brand": "Vivense", "sector": "Mobilya & Dekorasyon"},
    "Mondihome": {"brand": "Mondihome", "sector": "Mobilya & Dekorasyon"},
    "Alfemo": {"brand": "Alfemo", "sector": "Mobilya & Dekorasyon"},
    "Bellona": {"brand": "Bellona", "sector": "Mobilya & Dekorasyon"},
    "İstikbal": {"brand": "İstikbal", "sector": "Mobilya & Dekorasyon"},
    "Porland": {"brand": "Porland", "sector": "Mobilya & Dekorasyon"},
    "Karaca": {"brand": "Karaca", "sector": "Mobilya & Dekorasyon"},
    "English Home": {"brand": "English Home", "sector": "Mobilya & Dekorasyon"},
    "Madame Coco": {"brand": "Madame Coco", "sector": "Mobilya & Dekorasyon"},
    "Linens": {"brand": "Linens", "sector": "Mobilya & Dekorasyon"},
    "İdaş": {"brand": "İdaş", "sector": "Mobilya & Dekorasyon"},
    "Konfor": {"brand": "Konfor", "sector": "Mobilya & Dekorasyon"},
    "İder": {"brand": "İder Mobilya", "sector": "Mobilya & Dekorasyon"},
    "Mobilya": {"brand": None, "sector": "Mobilya & Dekorasyon"},
    "Ev Tekstili": {"brand": None, "sector": "Mobilya & Dekorasyon"},

    # ELEKTRONIK
    "Vestel": {"brand": "Vestel", "sector": "Elektronik"},
    "Arçelik": {"brand": "Arçelik", "sector": "Elektronik"},
    "Samsung": {"brand": "Samsung", "sector": "Elektronik"},
    "Beko": {"brand": "Beko", "sector": "Elektronik"},
    "Teknosa": {"brand": "Teknosa", "sector": "Elektronik"},
    "MediaMarkt": {"brand": "MediaMarkt", "sector": "Elektronik"},
    "Apple": {"brand": "Apple", "sector": "Elektronik"},
    "Dyson": {"brand": "Dyson", "sector": "Elektronik"},
    "Miele": {"brand": "Miele", "sector": "Elektronik"},
    "Casper": {"brand": "Casper", "sector": "Elektronik"},
    "Vaillant": {"brand": "Vaillant", "sector": "Elektronik"},
    "Beyaz Eşya": {"brand": None, "sector": "Elektronik"},
    "Elektronik": {"brand": None, "sector": "Elektronik"},
    
    # RESTORAN & KAFE
    "Yemeksepeti": {"brand": "Yemeksepeti", "sector": "Restoran & Kafe"},
    "Starbucks": {"brand": "Starbucks", "sector": "Restoran & Kafe"},
    "Kahve Dünyası": {"brand": "Kahve Dünyası", "sector": "Restoran & Kafe"},
    "Tavuk Dünyası": {"brand": "Tavuk Dünyası", "sector": "Restoran & Kafe"},
    "BigChefs": {"brand": "BigChefs", "sector": "Restoran & Kafe"},
    "Restoran": {"brand": None, "sector": "Restoran & Kafe"},
    "Kafe": {"brand": None, "sector": "Restoran & Kafe"},
    "Lokanta": {"brand": None, "sector": "Restoran & Kafe"},
    "Yemek": {"brand": None, "sector": "Restoran & Kafe"},
    "Burger King": {"brand": "Burger King", "sector": "Restoran & Kafe"},
    "McDonald's": {"brand": "McDonald's", "sector": "Restoran & Kafe"},
    
    # ANNE & BEBEK
    "Ebebek": {"brand": "Ebebek", "sector": "Anne, Bebek & Oyuncak"},
    "Toyzz Shop": {"brand": "Toyzz Shop", "sector": "Anne, Bebek & Oyuncak"},
    "Armağan Oyuncak": {"brand": "Armağan Oyuncak", "sector": "Anne, Bebek & Oyuncak"},
    
    # KAMPANYA TIPI / DIGER OZEL MARKALAR
    "Süpermarket": {"brand": None, "sector": "Market & Gıda"},
    "Market": {"brand": None, "sector": "Market & Gıda"},
    "Sunny": {"brand": "Sunny", "sector": "Elektronik"},
    "Silverline": {"brand": "Silverline", "sector": "Elektronik"},
    "Kumtel": {"brand": "Kumtel", "sector": "Elektronik"},
    "Vaillant": {"brand": "Vaillant", "sector": "Elektronik"},
    "Förni": {"brand": "Förni", "sector": "Mobilya & Dekorasyon"},
    "addresistanbul": {"brand": "addresistanbul", "sector": "Mobilya & Dekorasyon"},
    "Diyet": {"brand": None, "sector": "Kozmetik & Sağlık"},
    "TROY": {"brand": "TROY", "sector": "Finans & Yatırım"},

    # DIGER SEKTORLER (GENEL)
    "Sigorta": {"brand": None, "sector": "Sigorta"},
    "Emeklilik": {"brand": None, "sector": "Sigorta"},
    "BES": {"brand": None, "sector": "Sigorta"},
    "Hayat": {"brand": None, "sector": "Sigorta"},
    "Eğitim": {"brand": None, "sector": "Eğitim"},
    "Okul": {"brand": None, "sector": "Eğitim"},
    "Üniversite": {"brand": None, "sector": "Eğitim"},
    "Kurs": {"brand": None, "sector": "Eğitim"},
    "Kozmetik": {"brand": None, "sector": "Kozmetik & Sağlık"},
    "Sağlık": {"brand": None, "sector": "Kozmetik & Sağlık"},
    "Eczane": {"brand": None, "sector": "Kozmetik & Sağlık"},
    "Optik": {"brand": None, "sector": "Kozmetik & Sağlık"},
    "Sektör": {"brand": None, "sector": "Diğer"}, # Catch all fallback
    "Fatura": {"brand": None, "sector": "Fatura & Telekomünikasyon"},
    "Kültür": {"brand": None, "sector": "Kültür & Sanat"},
    "Sinema": {"brand": None, "sector": "Kültür & Sanat"},
    "Tiyatro": {"brand": None, "sector": "Kültür & Sanat"},
    "Konser": {"brand": None, "sector": "Kültür & Sanat"},
    "Bilet": {"brand": None, "sector": "Kültür & Sanat"},
    "Biletinial": {"brand": "Biletinial", "sector": "Kültür & Sanat"},
    "Otomotiv": {"brand": None, "sector": "Otomotiv"},
    "Servis": {"brand": None, "sector": "Otomotiv"},
    "Pirelli": {"brand": "Pirelli", "sector": "Otomotiv"},
    "Bağış": {"brand": None, "sector": "Hizmet & Bireysel Gelişim"},
    "Ders": {"brand": None, "sector": "Eğitim"},
    "Araç Kiralama": {"brand": None, "sector": "Ulaşım"},
    "Enterprise": {"brand": "Enterprise", "sector": "Ulaşım"},
    "Budget": {"brand": "Budget", "sector": "Ulaşım"},
    "Avis": {"brand": "Avis", "sector": "Ulaşım"},
    "Albafx": {"brand": "Albafx", "sector": "Finans & Yatırım"},
    "Enerya": {"brand": "Enerya", "sector": "Fatura & Telekomünikasyon"},
    "Setur": {"brand": "Setur", "sector": "Turizm & Konaklama"},
    "Qumpara": {"brand": "Qumpara", "sector": "E-Ticaret"},
    "Sigortam.net": {"brand": "Sigortam.net", "sector": "Sigorta"},
    "Raffles": {"brand": "Raffles", "sector": "Turizm & Konaklama"},
    "Sabiha Gökçen": {"brand": "Sabiha Gökçen", "sector": "Ulaşım"},
    "Monster": {"brand": "Monster", "sector": "Elektronik"},
    "Gürgençler": {"brand": "Gürgençler", "sector": "Elektronik"},
    "Koçtaş": {"brand": "Koçtaş", "sector": "Mobilya & Dekorasyon"},
    "Evidea": {"brand": "Evidea", "sector": "Mobilya & Dekorasyon"},
    "Jumbo": {"brand": "Jumbo", "sector": "Mobilya & Dekorasyon"},
    "Enza Home": {"brand": "Enza Home", "sector": "Mobilya & Dekorasyon"},
    "Divanev": {"brand": "Divanev", "sector": "Mobilya & Dekorasyon"},
    "Puffy": {"brand": "Puffy", "sector": "Mobilya & Dekorasyon"},
    
    # BANKA KARTLARI & MOBIL APP (FALLBACK)
    "Parafly": {"brand": None, "sector": "Turizm & Konaklama"},
    "Wings": {"brand": None, "sector": "Turizm & Konaklama"},
    "Adios": {"brand": None, "sector": "Turizm & Konaklama"},
    "Miles&Smiles": {"brand": None, "sector": "Ulaşım"},
    "Paraf": {"brand": None, "sector": "Diğer"},
    "Bonus": {"brand": None, "sector": "Diğer"},
    "World": {"brand": None, "sector": "Diğer"},
    "Maximum": {"brand": None, "sector": "Diğer"},
    "Axess": {"brand": None, "sector": "Diğer"},
    "Bankkart": {"brand": None, "sector": "Diğer"},
    "HSBC": {"brand": None, "sector": "Diğer"},
    "TEB": {"brand": None, "sector": "Diğer"},
    "Vakıfbank": {"brand": None, "sector": "Diğer"},
    "Albaraka": {"brand": None, "sector": "Diğer"},
    "QNB": {"brand": None, "sector": "Diğer"},
}

def run_diagnostic():
    engine = create_engine(os.getenv('DATABASE_URL'))
    
    # Get all campaigns
    query = "SELECT id, title, description FROM campaigns"
    
    matches = []
    no_matches = []
    
    with engine.connect() as conn:
        campaigns = conn.execute(text(query)).fetchall()
        
        for c_id, title, desc in campaigns:
            full_text = f"{title} {desc if desc else ''}"
            matched = False
            
            for keyword, data in MATCH_RULES.items():
                # Case insensitive match with word boundaries and optional Turkish suffixes
                # This regex catches 'idefix'te', 'Albafx’te', etc.
                pattern = r'(?i)\b' + re.escape(keyword) + r"(['’]?[a-zçğıöşü]*)?\b"
                if re.search(pattern, full_text):
                    matches.append({
                        "id": c_id,
                        "title": title,
                        "suggested_brand": data["brand"],
                        "suggested_sector": data["sector"]
                    })
                    matched = True
                    break
            
            if not matched:
                no_matches.append({"id": c_id, "title": title})

    print(f"\n📊 --- POINT-BLANK TEŞHİS RAPORU ---")
    print(f"Toplam Kampanya: {len(campaigns)}")
    print(f"Sözlükle Eşleşen: {len(matches)} (%{len(matches)/len(campaigns)*100:.1f})")
    print(f"Eşleşmeyen: {len(no_matches)} (%{len(no_matches)/len(campaigns)*100:.1f})")
    
    print("\n✅ ÖRNEK EŞLEŞMELER:")
    for m in matches[:15]:
        brand_str = m['suggested_brand'] if m['suggested_brand'] else "Sektörel Eşleşme"
        print(f"- [{brand_str} | {m['suggested_sector']}] -> {m['title']}")
        
    print("\n❌ EŞLEŞMEYEN ÖRNEKLER (Eğitilmesi Gerekenler):")
    for nm in no_matches[:10]:
        print(f"- {nm['title']}")

if __name__ == "__main__":
    run_diagnostic()
