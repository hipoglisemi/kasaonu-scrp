import urllib.request
import re

url = "https://www.pexels.com/search/finance/"
req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64)'})
try:
    html = urllib.request.urlopen(req).read().decode('utf-8')
    matches = re.findall(r'images.pexels.com/photos/(\d+)/', html)
    matches = list(set(matches))
    print(f"Found {len(matches)} Pexels IDs!")
    print(matches[:5])
except Exception as e:
    print("Failed:", e)
