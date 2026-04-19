from bs4 import BeautifulSoup
import re

with open("scratch/maximum_test.html", "r", encoding="utf-8") as f:
    html = f.read()

soup = BeautifulSoup(html, "html.parser")
title_el = soup.find("h1")
print(f"Title: {title_el.text.strip() if title_el else 'No Title'}")

selectors = [".campaign-detail", ".campaignDetail", ".content", ".detail-content", ".editor-content"]
desc_el = soup.select_one(", ".join(selectors))

if desc_el:
    print(f"Found desc_el with classes: {desc_el.get('class')}")
    text = desc_el.get_text(separator="\n", strip=True)
    print("Length:", len(text))
    print("Content preview:", text[:200].replace("\n", " "))
else:
    print("None of the standard selectors worked. Searching for keywords...")
    # Look for "Koşullar", "Katılım", etc.
    candidate = soup.find(string=re.compile(r"Kampanya Detayları|Kampanya Koşulları"))
    if candidate and candidate.parent:
        print("Found a keyword context")
        p = candidate.parent
        while p and len(p.get_text()) < 200:
            p = p.parent
        print(f"Parent class: {p.get('class')}")
        print("Extract preview:", p.get_text(separator="\n", strip=True)[:200].replace("\n", " "))
