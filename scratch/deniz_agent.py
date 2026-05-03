from selenium import webdriver
import time
from bs4 import BeautifulSoup

options = webdriver.ChromeOptions()
options.add_argument('--window-size=390,844')
options.add_argument('--user-agent=Mozilla/5.0 (iPhone; CPU iPhone OS 16_6 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/16.6 Mobile/15E148 Safari/604.1')
options.add_argument('--headless=new')

print("Browser starting...")
driver = webdriver.Chrome(options=options)
driver.get("https://www.denizbonus.com/kampanyalar/internet-alisverislerine-2000-tlye-varan-bonus")

time.sleep(5)
driver.execute_script("window.scrollTo(0, document.body.scrollHeight/2);")
time.sleep(3)
driver.execute_script("window.scrollTo(0, document.body.scrollHeight);")
time.sleep(3)

html = driver.page_source
driver.quit()

soup = BeautifulSoup(html, "html.parser")
katil = soup.find(lambda t: t.name and t.text and "ECOM" in t.text)
if katil:
    print("\n--- BULUNDU! ---")
    print("Class names:", katil.get('class'))
    print("Tag name:", katil.name)
    print("Parent class:", katil.parent.get('class') if katil.parent else "None")
    print("Parent Parent class:", katil.parent.parent.get('class') if katil.parent and katil.parent.parent else "None")
    print("Text:", katil.text.strip())
else:
    print("\n--- BULUNAMADI! ECOM KELİMESİ YOK ---")
    
