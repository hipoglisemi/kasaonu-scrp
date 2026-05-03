import sys
project_root = "/Users/hipoglisemi/Desktop/kartavantaj-scraper"
sys.path.insert(0, project_root)

from src.services.negation_filter import check_string_negation, normalize_text

text = "Kampanyaya bireysel kartlar, Wings Business, Bank'O Card Axess (Odea Bank) ve banka kartları dahil değildir."
text_norm = normalize_text(text)

target = "Wings Business"
target_norm = normalize_text(target)

print(f"Text Norm: {text_norm}")
print(f"Target Norm: {target_norm}")

is_negated = check_string_negation(target, text_norm, bank_key="akbank")
print(f"Is '{target}' negated? {is_negated}")

# Test with a simpler one
text2 = "Wings dahil değildir."
print(f"Is 'Wings' negated in '{text2}'? {check_string_negation('Wings', normalize_text(text2))}")
