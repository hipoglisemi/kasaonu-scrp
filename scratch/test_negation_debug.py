import sys
project_root = "/Users/hipoglisemi/Desktop/kartavantaj-scraper"
sys.path.insert(0, project_root)
from src.services.negation_filter import check_string_negation, normalize_text

text = "Artı taksit imkanına bireysel kartlar, Axess Business Free ve Bank’O Card Axess dahil değildir."
text_norm = normalize_text(text)

print(f"TEXT NORM: {text_norm}")

target = "Bank’O Card Axess"
is_negated = check_string_negation(target, text_norm, bank_key="akbank")
print(f"Is '{target}' negated? {is_negated}")

target2 = "Bank'o Card"
is_negated2 = check_string_negation(target2, text_norm, bank_key="akbank")
print(f"Is '{target2}' negated? {is_negated2}")
