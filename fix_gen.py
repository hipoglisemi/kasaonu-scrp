import re

pool_logic = """import json
import random
import os

pool_path = os.path.join(os.path.dirname(__file__), 'unsplash_pool.json')
try:
    with open(pool_path, 'r') as f:
        UNSPLASH_POOL = json.load(f)
except Exception:
    UNSPLASH_POOL = {'finance': ['1FxMET2U5dU']}

def get_unsplash_url(title: str) -> str:
    \"\"\"Blog başlığına göre yüzlerce gerçek Unsplash ID'sinden benzersiz bir görsel seçer.\"\"\"
    t = str(title).lower()
    cat = 'finance'
    
    if 'uçak' in t or 'seyahat' in t or 'otel' in t: cat = 'travel'
    elif 'market' in t or 'gıda' in t: cat = 'grocery'
    elif 'e-ticaret' in t or 'alışveriş' in t: cat = 'shopping'
    elif 'akaryakıt' in t or 'araç' in t or 'otomotiv' in t: cat = 'driving'
    elif 'sağlık' in t or 'kozmetik' in t: cat = 'health'
    elif 'teknoloji' in t or 'elektronik' in t: cat = 'technology'
    elif 'mobilya' in t or 'dekorasyon' in t: cat = 'interior-design'
    
    lst = UNSPLASH_POOL.get(cat)
    if not lst or len(lst) == 0:
        lst = UNSPLASH_POOL.get('finance', ['1FxMET2U5dU'])
        
    img_id = random.choice(lst)
    return f"https://images.unsplash.com/photo-{img_id}?w=1200&q=80&auto=format&fit=crop"
"""

for fname in ['generate_seo_blog.py', 'auto_seo_pillar_generator.py']:
    with open(fname, 'r') as f:
        content = f.read()

    # Find the def get_unsplash_url block and replace it
    pattern = re.compile(r'def get_unsplash_url\(title.*?return f"https://source.unsplash.com/random.*?"', re.DOTALL)
    
    # We also need to add the json import if not there, but pool_logic replaces the fn
    # wait my target string didn't have the def line.
    
    # let's just replace from import random down to the return
    pattern2 = re.compile(r'import random\nimport time\n+def get_unsplash_url.*?return f"https://source.unsplash.com.*?"', re.DOTALL)
    
    # if it has loremflickr
    pattern3 = re.compile(r'def get_unsplash_url.*?return f"https://loremflickr.com.*?"', re.DOTALL)

    content = re.sub(pattern2, pool_logic, content)
    content = re.sub(pattern3, pool_logic, content)
    
    with open(fname, 'w') as f:
        f.write(content)

print("✅ Both generators hard-wired to massive local pool!")
