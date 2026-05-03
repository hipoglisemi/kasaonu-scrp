
import sys
import os

# Add current directory to path
sys.path.append('/Users/hipoglisemi/Desktop/kartavantaj-scraper')

from src.services.negation_filter import filter_excluded_cards

text = "Paraf, Parafly, sanal kartlar ve ek kartlar kampanyaya dahildir. Paraf Gençİz, Paraf Genç, banka kartları, ticari kartlar, Halkcard'lar, ParafPara kullanarak yapılan işlemler, iptal ve iade işlemleri kampanyaya dahil değildir."
cards = ["Paraf", "Parafly", "Sanal kartlar", "Ek kartlar", "Paraf Gençiz", "Paraf Genç"]

filtered = filter_excluded_cards(cards, text)
print(f"\nOriginal Cards: {cards}")
print(f"Filtered Cards: {filtered}")
