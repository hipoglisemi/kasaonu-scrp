from src.services.negation_filter import check_string_negation

raw_text = """
1 Mayıs - 31 Mayıs 2026 tarihleri arasında, www.idas.com.tr ’de ve kampanyaya dahil İdaş Mobilya mağazalarında yapılacak alışverişlerde peşin fiyatına 9 taksit sunulmaktadır.
Kampanyadan Axess, Wings, Free ve Ticari kart sahipleri faydalanabilir.
Ticari kredi kartları ile en fazla 6 taksit yapılabilmektedir.
Kampanyaya katılan Axess üyesi İdaş Mobilya işyeri listesine https://www.axess.com.tr//9042 adreslerinden ulaşabilirsiniz.
"""
print("Axess:", check_string_negation("axess", raw_text, "akbank", True))
print("Wings:", check_string_negation("wings", raw_text, "akbank", True))
print("Free:", check_string_negation("free", raw_text, "akbank", False))
print("Ticari:", check_string_negation("ticari", raw_text, "akbank", False))
