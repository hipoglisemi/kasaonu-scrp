import re

text = "Öne Çıkan Kampanyalar".translate({ord('I'): 'ı', ord('İ'): 'i', ord('Ş'): 'ş', ord('Ğ'): 'ğ', ord('Ç'): 'ç', ord('Ö'): 'ö', ord('Ü'): 'ü'}).lower()

print(f"text_lower: '{text}'")

marker = r"(?i)öne çıkan kampanyalar"
match = re.search(marker, text, re.MULTILINE)
print("Match 'öne çıkan':", match)

marker_2 = r"(?i)ilgili kampanyalar"
match_2 = re.search(marker_2, text, re.MULTILINE)
print("Match 'ilgili':", match_2)

text2 = "Diğer Kampanyalar".translate({ord('I'): 'ı', ord('İ'): 'i', ord('Ş'): 'ş', ord('Ğ'): 'ğ', ord('Ç'): 'ç', ord('Ö'): 'ö', ord('Ü'): 'ü'}).lower()
print(f"text2_lower: '{text2}'")
marker_3 = r"(?i)diğer kampanyalar"
match_3 = re.search(marker_3, text2, re.MULTILINE)
print("Match 'diğer':", match_3)
