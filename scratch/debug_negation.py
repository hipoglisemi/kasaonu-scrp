import sys
import os
import re

# Proje kök dizinini ekle
project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if project_root not in sys.path:
    sys.path.insert(0, project_root)

from src.services.negation_filter import check_string_negation, normalize_text, NEGATION_KEYWORDS

full_text = """Axess Öğrenci kartına şimdi başvuran Akbanklılar, 1.200 TL’ye varan chip-para kazanıyor!
Sen de 31 Mayıs’a kadar Axess Öğrenci kartına başvurabilir ve Juzdan’dan kampanyaya katılarak 15 Haziran tarihine kadar her 500 TL ve üzeri harcamaya 300 TL, toplamda 1.200 TL'ye varan chip-para kazabilirsiniz.
Kazanmak için şimdi Axess’e başvurup Juzdan’dan kampanyaya katılabilirsin.
Üstelik ilk yıl kart ücreti ödemeden!
Kampanya detayları:
Kampanyaya, Akbank bireysel kredi kartı olmayıp 1 – 31 Mayıs 2026 tarihleri arasında ilk kez Axess Öğrenci kartı başvurusu yapan Akbanklılar 31 Mayıs 2026 tarihine kadar katılabilirler.
1 – 31 Mayıs 2026 tarihleri arasında başvurusu onaylanan Akbanklılar kampanya kapsamında 15 Haziran 2026 tarihine kadar yapacakları her 500 TL ve üzeri harcamaya 300 TL, toplam 1.200 TL’ye varan chip-para kazanabilirler.
Akbank Mobil, Akbank İnternet, Juzdan, akbank.com, axess.com.tr, ATM’lerimiz, şubelerimiz ve Müşteri İletişim Merkezimizden kredi kartı başvurusunda bulunabilirsiniz.
Kampanyadan sadece 18-26 yaş arasındaki asıl Axess Öğrenci kredi kartı sahipleri yararlanabilirler.
Juzdan veya Akbank Mobil’den kampanyaya katılmak için harcamadan önce “Hemen katıl” butonuna tıklamanız gerektiğini bilmenizi isteriz. Kampanya, profil alanındaki “Kampanyalarınız” başlığı altında göründükten sonra katılım gerçekleşir.
SMS ile kampanyaya katılmak için ilk harcamadan önce bankamızın sistemine kayıtlı olan cep telefonu numaranızdan “OGRENCIKAZAN” yazıp 4566’ya SMS göndererek kaydolmanız gerektiğini bildirmek isteriz. Belirtilen kısa mesajın bankamızın sistemine ulaşmasından sonra bankamızca size “kaydoldunuz” bilgisinin iletilmesi ile kampanyaya katılımınız gerçekleşir. Katılım için gönderilen SMS’lerin operatörlerin kendi tarifelerinden ücretlendirildiğini bilmenizi isteriz.
Kampanya bireysel bazda düzenlenir.
Bir katılımcı kampanyadan en fazla 1.200 TL chip-para kazanabilir.
Yurt dışı işlemlerin kampanyaya dâhil olmadığını belirtmek isteriz.
Axess, Wings, ticari kartlar, Free, Akbank Kart ve Bank’O Card Axess’in kampanyaya dâhil olmadığını hatırlatırız.
Aynı gün aynı iş yerinden yapılan yalnızca ilk işlem kampanyaya dâhil edilir.
Hak edilen chip-paralar işlem anında harcamanın yapıldığı karta yüklenir.
İptal ve iade işlemlerinde yüklenen chip-para geri alınır. Chip-paranın kullanılmış ise ekstreye ilgili tutar kadar borç yansıtılır."""

text_norm = normalize_text(full_text)
print(f"DEBUG: text_norm contains 'dahil olmadigini': {'dahil olmadigini' in text_norm}")

cards_to_test = ["Axess", "Wings", "ticari kartlar", "Free", "Bank’O Card Axess"]

for card in cards_to_test:
    is_negated = check_string_negation(card, text_norm, bank_key="akbank")
    print(f"Card: {card:20} | Negated: {is_negated}")

# Test the positive check regex specifically
sentence = "axess, wings, ticari kartlar, free, akbank kart ve bank'o card axess'in kampanyaya dahil olmadigini hatirlatiriz"
pos_check = re.search(r"(?i)(?:^|\s|,)dahil(?![\s]*(?:degil|olmadigini|olmadigi))", sentence)
print(f"Positive Check Match: {pos_check}")
