import sys
import os

project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, project_root)

from src.services.text_cleaner import clean_campaign_text

html = open("scratch/deniz_agent_html.txt", "w")

from selenium import webdriver
import time
options = webdriver.ChromeOptions()
options.add_argument('--window-size=390,844')
options.add_argument('--headless=new')
driver = webdriver.Chrome(options=options)
driver.get("https://www.denizbonus.com/kampanyalar/internet-alisverislerine-2000-tlye-varan-bonus")
time.sleep(5)
driver.execute_script("window.scrollTo(0, document.body.scrollHeight);")
time.sleep(3)
raw_html = driver.page_source
driver.quit()

html.write(raw_html)
html.close()

cleaned = clean_campaign_text(raw_html, "İnternet Alışverişlerinize", "İnternet Alışverişlerinize")
print("--- CLEANED TEXT START ---")
print(cleaned)
print("--- CLEANED TEXT END ---")
print("\nECOM VAR MI:", "ECOM" in cleaned)
