import requests
import json
import time

CATEGORIES = ['finance', 'shopping', 'grocery', 'travel', 'technology', 'driving', 'health', 'interior-design', 'banking', 'credit card']
PAGES = 2 # 2 pages per category * 20 photos = 40 photos per category = 400 photos total

pool = {}

headers = {"User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36"}

for cat in CATEGORIES:
    pool[cat] = []
    for page in range(1, PAGES + 1):
        url = f"https://unsplash.com/napi/search/photos?query={cat}&per_page=20&page={page}"
        try:
            resp = requests.get(url, headers=headers)
            if resp.status_code == 200:
                data = resp.json()
                for img in data.get('results', []):
                    pool[cat].append(img['id'])
        except Exception as e:
            print(f"Error fetching {cat}: {e}")
        time.sleep(1) # respectful delay

# ensure unique
for cat in CATEGORIES:
    pool[cat] = list(set(pool[cat]))

with open('unsplash_pool.json', 'w') as f:
    json.dump(pool, f, indent=2)

print(f"✅ Downloaded {sum(len(v) for v in pool.values())} unique high-quality Unsplash image IDs across {len(CATEGORIES)} categories!")
