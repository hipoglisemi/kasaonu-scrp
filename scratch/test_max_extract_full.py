from bs4 import BeautifulSoup

def _clean(text):
    import re
    if not text: return ""
    return re.sub(r"\s+", " ", text.replace("\n", " ").replace("\r", "")).strip()

def test_maximiles_extraction():
    url = "https://www.maximiles.com.tr/kampanyalar/hepsiburada-da-pesin-fiyatina-6-taksit-firsati"
    html = open("scratch/max_hepsi.html", "r", encoding="utf-8").read()
    soup = BeautifulSoup(html, "html.parser")
    
    content_parts = []
    selectors = [".page-content", "section div.container", ".detail-text", ".campaign-content", ".text-area", ".content", ".content-part", "table"]
    
    print("Finding containers...")
    for sel in selectors:
        containers = soup.select(sel)
        for container in containers:
            text = container.get_text(separator="\n", strip=True)
            if len(text) > 150 and "Ana Sayfa" not in text[:80] and "Maximum Mobil" not in text[:50]:
                is_duplicate = False
                for existing_part in content_parts:
                    if text[:100] in existing_part or existing_part[:100] in text:
                        is_duplicate = True
                        break
                if not is_duplicate:
                    content_parts.append(text)
                    print(f"Added part from {sel}, length {len(text)}")
                    
    raw_text = "\n---\n".join(content_parts)
    print("TOTAL RAW TEXT GENERATED:")
    print("====================================")
    print(raw_text)
    print("====================================")

    import sys
    sys.path.append("/Users/hipoglisemi/Desktop/kartavantaj-scraper")
    from src.services.text_cleaner import clean_campaign_text
    
    title = "Hepsiburada’da Peşin Fiyatına 6 Taksit Fırsatı!"
    clean_text = clean_campaign_text(raw_text, title)
    
    print("TOTAL CLEAN TEXT GENERATED:")
    print("====================================")
    print(clean_text)
    print("====================================")

if __name__ == "__main__":
    test_maximiles_extraction()
