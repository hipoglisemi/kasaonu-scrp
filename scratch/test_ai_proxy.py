import sys
sys.path.append("/Users/hipoglisemi/Desktop/kartavantaj-scraper")
from src.services.ai_parser import AIParser
from scratch.test_max_extract_full import test_maximiles_extraction

# Just use a dummy raw_text
raw_text = "31 Mart tarihine kadar Maximum Kart'ınız ile Hepsiburada'dan yapacağınız; 3.000 TL ve üzeri alışverişlerinizde peşin fiyatına 3 taksit, 15.000 TL ve üzeri alışverişlerinizde peşin fiyatına 6 taksit fırsatlarından yararlanabilirsiniz. Kampanyaya dâhil olan kartlar: İş Bankası Maximum ve Maximiles özellikli bireysel kredi kartları Ek Koşullar: Ürün gruplarında uygulanacak taksit adetleri 10 Mart 2007 tarihinde."
title = "Hepsiburada’da Peşin Fiyatına 6 Taksit Fırsatı!"
bank_name = "işbankası"

parser = AIParser()
res = parser.parse_campaign_data(raw_text=raw_text, title=title, bank_name=bank_name)
print("KEYS RETURNED:")
for k, v in res.items():
    print(f"{k}: {str(v)[:100]}")
