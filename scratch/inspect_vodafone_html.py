import requests
from bs4 import BeautifulSoup

def inspect():
    url = "https://www.vodafone.com.tr/kampanyalar/saw-hediye-firsati"
    headers = {
        "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    }
    r = requests.get(url, headers=headers)
    soup = BeautifulSoup(r.text, 'html.parser')
    
    print("=== H1 Tags ===")
    for h1 in soup.find_all('h1'):
        print(f"H1: '{h1.get_text(strip=True)}' | Class: {h1.get('class')}")
        
    print("\n=== H2 Tags ===")
    for h2 in soup.find_all('h2'):
        print(f"H2: '{h2.get_text(strip=True)}' | Class: {h2.get('class')}")

    print("\n=== H3 Tags ===")
    for h3 in soup.find_all('h3'):
        print(f"H3: '{h3.get_text(strip=True)}' | Class: {h3.get('class')}")

    print("\n=== Title Element ===")
    if soup.title:
        print(f"Title Tag: '{soup.title.get_text(strip=True)}'")
        
    print("\n=== Title selector check ===")
    print(f".gallery--header h1: {soup.select_one('.gallery--header h1')}")

if __name__ == "__main__":
    inspect()
