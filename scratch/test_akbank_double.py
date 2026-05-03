import sys
import os
# Path setup
project_root = "/Users/hipoglisemi/Desktop/kartavantaj-scraper"
if project_root not in sys.path:
    sys.path.insert(0, project_root)

from src.services.ai_parser_golden import AIParserGolden
from unittest.mock import MagicMock

# Mock model client
mock_client = MagicMock()
mock_client.generate_content.return_value = """
{
  "title": "Wings’e özel WMF Mağazalarında 20.000 Mil Puan!",
  "description": "Wings kartınızla WMF mağazalarında yapacağınız 10.000 TL ve üzeri alışverişlerinize 20.000 Mil Puan kazanın.",
  "ai_marketing_text": "Wings ile WMF'de mil yağmuru! 20.000 Mil Puan kazanma fırsatını kaçırmayın. ✈️",
  "reward_value": 20000.0,
  "reward_type": "mil",
  "reward_text": "20.000 Mil Puan",
  "min_spend": 10000.0,
  "start_date": "2026-04-20",
  "end_date": "2026-05-20",
  "sector": "elektronik",
  "brands": ["WMF"],
  "cards": ["Bireysel Wings", "Ticari Wings", "Ek kartlar"],
  "participation": "Juzdan'dan 'Hemen Katıl'a tıklayın veya WMF yazıp 4566'ya SMS gönderin.",
  "conditions": [
    "10.000 TL ve üzeri ilk alışverişte geçerlidir.",
    "Kampanyadan bir müşteri en fazla 20.000 Mil Puan kazanabilir.",
    "İnternet sitesinden yapılan alışverişler dahil değildir.",
    "Peşin fiyatına 6 taksit fırsatından Axess, Wings, Free, Akbank Kart ve Ticari kartlar faydalanabilir.",
    "Taksit kampanyası 3.500 TL ve üzeri alışverişlerde geçerlidir.",
    "Axess, Free, Akbank Kart Mil Puan kampanyasına dahil değildir."
  ]
}
"""

parser = AIParserGolden(model_client=mock_client)
text = """
Wings’e özel 20 Nisan - 20 Mayıs 2026 tarihleri arasında kampanyaya dahil WMF mağazalarında 10.000 TL ve üzeri ilk alışverişinize 20.000 Mil Puan ayrıcalığı sunulmaktadır. 
Mil Puan kampanyasına, Juzdan üzerinden kampanyaya katılmak için harcamadan önce “Hemen Katıl” butonu tıklanmalıdır. Kampanyanın profil alanındaki “Kampanyalarınız” başlığı altında görünmesinden sonra kampanyaya katılım sağlanır. SMS ile kampanyaya katılmak için, ilk harcamadan önce Akbank sistemine kayıtlı olan cep telefonu numarasından "WMF" yazıp 4566’ya SMS göndererek kayıt olmak gerekmektedir. Belirtilen kısa mesajın Akbank sistemine ulaşmasından ve Akbank tarafından ‘kayıt oldunuz’ bilgisinin tarafınıza iletilmesinden sonra kampanyaya katılım sağlamış olursunuz. Katılım için gönderilen SMS’ler operatörlerin kendi tarifeleri üzerinden ücretlendirilir.
Mil Puan kampanyasına bireysel ve ticari Wings kartlar ile bu kartlara bağlı ek kartlar dahildir. Axess, Free, Akbank Kart, Bank’O Card Axess ve sanal kartlar kampanyaya dahil değildir.
Mil Puan kampanyasına www.wmf.com.tr’den yapılan alışverişler dahil değildir.
Kazanılan Mil Puanlar kampanya koşulları gerçekleştirildikten sonra iki iş günü içinde yüklenecektir.
Kampanyadan bir müşteri bir kez faydalanabilecektir ve en fazla 20.000 Mil Puan kazanabilecektir. Mil Puan veya chip-para kullanılarak yapılan alışverişler kampanyaya dahil değildir. Nakit çekim, eft/havale, fon alım/satım, BES işlemleri, anlık/otomatik fatura, vergi ödemeleri ve chip-para ile yapılan alışverişler kampanyaya dahil değildir. İptal ve iade işlemlerinde yüklenen Mil Puan iade alınacaktır. Mil Puanın kullanılmış olması halinde ekstreye borç yansıtılacaktır. 
Peşin fiyatına taksit kampanyasından Axess, Wings, Free, Akbank Kart ve Ticari kartlar ile bu kartlara bağlı ek kartlar ve sanal kartlar faydalanabilir. Bank’O Card Axess kartlar kampanyaya dahil değildir.
Taksit kampanyası kapsamında, 3.500 TL ve üzeri olan alışverişlerde peşin fiyatına 6 taksit geçerlidir.
Ticari kredi kartları ile en fazla 6 taksit yapılabilmektedir.
Kampanya kapsamındaki mağaza harcamalarının, Akbank Axess POS uygulaması yüklü terminalden yapılması gerekmektedir.
Mil Puan kampanyası için Juzdan veya SMS ile kayıt olmayan kart sahiplerinin harcamaları kampanya kapsamında değerlendirilmeyecektir. Taksit kampanyasına katılım şartı bulunmamaktadır.
"""

result = parser.parse_campaign(text, bank_name="Akbank", title="WMF Mil Puan")
print(f"Final Cards: {result['cards']}")
print(f"Final Conditions: {result['conditions']}")
