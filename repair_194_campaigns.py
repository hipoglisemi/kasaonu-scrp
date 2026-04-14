import os
import sys
import re
import time
import unicodedata
from sqlalchemy.orm import joinedload
sys.path.append(os.getcwd())

os.environ["GEMINI_MODEL"] = "gemini-2.5-flash-lite"
from src.database import get_db_session
from src.models import Campaign, CampaignBrand, Card
from src.services.ai_parser import AIParser

def tr_lower(text): return text.replace('İ', 'i').replace('I', 'ı').lower()
def clean_ws(t): return re.sub(r'\s+', ' ', t).strip()

def create_slug(text):
    text = str(text)
    text = text.replace('ı', 'i').replace('ş', 's').replace('ğ', 'g').replace('ü', 'u').replace('ö', 'o').replace('ç', 'c')
    text = text.replace('I', 'i').replace('Ş', 's').replace('Ğ', 'g').replace('Ü', 'u').replace('Ö', 'o').replace('Ç', 'c')
    text = unicodedata.normalize('NFKD', text).encode('ascii', 'ignore').decode('utf-8').lower()
    return re.sub(r'[^a-z0-9]+', '-', text).strip('-')

negation_keywords = ['dahil değildir', 'hariçtir', 'geçerli değildir', 'kapsam dışıdır', 'dahil edilmeyecektir', 'sayılmamaktadır', 'taksitlendirilmemektedir']
positive_keywords = ['geçerlidir', 'dahildir', 'geçerli olacaktır']
PARTIAL_EXCLUSION_WORDS = ['belirli', 'seçili', 'bazı', 'haricindeki', 'dışındaki', 'markalı', 'kategorisindeki']
NOISE_MARKERS = [r'ilginizi çekebilecek diğer kampanyalar', r'benzer fırsatlar', r'benzer kampanyalar', r'diğer kampanyalar', r'sizin için seçtiklerimiz']

def _get_194_campaign_ids():
    target_ids = []
    with get_db_session() as db:
        campaigns = db.query(Campaign).options(joinedload(Campaign.brands).joinedload(CampaignBrand.brand)).all()
        for c in campaigns:
            if not c.brands: continue
            full_context = (c.clean_text or c.description or '') + '\n' + (c.conditions or '')
            full_context_lower = tr_lower(full_context)
            title_lower = tr_lower(c.title or '')
            clean_context = clean_ws(full_context_lower)

            rejected_reason = None
            for cb in c.brands:
                brand_norm = tr_lower(cb.brand.name)
                if len(brand_norm) < 2: continue
                if brand_norm in re.sub(r'[^a-z0-9ıişğüç ]', ' ', title_lower) or brand_norm in title_lower: continue

                clean_brand = clean_ws(brand_norm)
                for marker in NOISE_MARKERS:
                    match = re.search(marker, full_context_lower, re.IGNORECASE)
                    if match:
                        pos = match.start()
                        bpat = rf'(?i)\b{re.escape(brand_norm)}\b'
                        if re.search(bpat, full_context_lower[pos:]) and not re.search(bpat, full_context_lower[:pos]):
                            rejected_reason = 'İllüzyon'
                            break
                if rejected_reason: break
                
                b_indices = [m.start() for m in re.finditer(rf'(?i)\b{re.escape(clean_brand)}\b', clean_context)]
                n_indices = [m.start() for neg in negation_keywords for m in re.finditer(re.escape(neg), clean_context)]
                p_indices = [m.start() for pos in positive_keywords for m in re.finditer(re.escape(pos), clean_context)]
                for b_idx in b_indices:
                    is_valid = any(abs(b_idx - p_idx) < 100 for p_idx in p_indices)
                    has_exc = False
                    for n_idx in n_indices:
                        if abs(b_idx - n_idx) < 150:
                            snippet = clean_context[min(b_idx, n_idx):max(b_idx, n_idx)+len(clean_brand)+20]
                            if any(p in snippet for p in PARTIAL_EXCLUSION_WORDS): continue
                            has_exc = True
                            break
                    if has_exc and not is_valid:
                        rejected_reason = 'Kısıtlama'
                        break
                if rejected_reason: break
                
            if rejected_reason: target_ids.append(c.id)
    return target_ids

def main():
    target_ids = _get_194_campaign_ids()
    print(f"[{os.environ['GEMINI_MODEL']}] Toplam {len(target_ids)} adet kusurlu ID tespit edildi. Onarım başlıyor...")
    
    parser = AIParser()
    success_count = 0
    fail_count = 0
    
    from src.models import Brand
    from src.services.brand_normalizer import cleanup_brands
    
    for cid in target_ids:
        with get_db_session() as db:
            c = db.query(Campaign).options(
                joinedload(Campaign.brands).joinedload(CampaignBrand.brand),
                joinedload(Campaign.card).joinedload(Card.bank)
            ).filter(Campaign.id == cid).first()
            if not c: continue
            
            old_brands = [cb.brand.name for cb in c.brands]
            full_context = (c.clean_text or c.description or '') + '\n' + (c.conditions or '')
            bank_name = c.card.bank.name if c.card and c.card.bank else ""
            title = c.title
            
        print(f"ID: {cid} | Eski: {old_brands} -> AI Okuyor...")
        
        try:
            parsed_data = parser.parse_campaign_data(full_context, title=title, bank_name=bank_name)
            
            if "error" in parsed_data:
                print(f"    ❌ AI Çöktü/Hata Döndü. Atlanıyor! Hata: {parsed_data['error']}")
                fail_count += 1
                time.sleep(1)
                continue
                
            ai_brands_raw = parsed_data.get("brands", [])
            cleaned_ai_brands = cleanup_brands(ai_brands_raw)
            final_validated_brands = parser._validate_brands_against_text(cleaned_ai_brands, full_context, title)
            
            print(f"    AI Kararı: {final_validated_brands}")
            
            with get_db_session() as db_write:
                if set(old_brands) != set(final_validated_brands):
                    removed = set(old_brands) - set(final_validated_brands)
                    added = set(final_validated_brands) - set(old_brands)
                    print(f"    ✨ İşlem: Silinen: {removed}, Eklenen: {added}")
                    
                    db_write.query(CampaignBrand).filter(CampaignBrand.campaign_id == cid).delete()
                    db_write.commit()
                    
                    for brand_name in final_validated_brands:
                        brand_record = db_write.query(Brand).filter(Brand.name == brand_name).first()
                        if not brand_record:
                            print(f"      + Yeni Marka Yaratılıyor: {brand_name}")
                            b_slug = create_slug(brand_name)
                            brand_record = Brand(name=brand_name, slug=b_slug)
                            db_write.add(brand_record)
                            db_write.commit()
                            db_write.refresh(brand_record)
                            
                        new_link = CampaignBrand(campaign_id=cid, brand_id=brand_record.id)
                        db_write.add(new_link)
                    db_write.commit()
                    success_count += 1
                else:
                    print(f"    ℹ️ Değişiklik yok.")
            
        except Exception as e:
            print(f"HATA ID {cid}: {e}")
            fail_count += 1
            
        time.sleep(0.5)

    print(f"\n--- ONARIM TAMAMLANDI ---\nBaşarılı DB Güncellemesi: {success_count}\nHatalı Gönderim / Pas Geçilen: {fail_count}")

if __name__ == "__main__":
    main()
