import requests
url = "https://www.ziraatdinamik.com.tr/tr/kendim-icin/kampanyalar/Ikea-da-6-Taksit-Firsati"
session = requests.Session()
session.headers.update({
    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
})
print(f"Fetching {url}")
try:
    resp = session.get(url, timeout=10)
    print(f"Status: {resp.status_code}")
    print(resp.text[:500])
except Exception as e:
    print(f"Error: {e}")
