import asyncio
from playwright.async_api import async_playwright
import json

async def main():
    async with async_playwright() as p:
        browser = await p.chromium.launch()
        page = await browser.new_page()
        
        apis = []
        page.on('response', lambda response: apis.append(response.url))
        
        await page.goto('https://pokus.com.tr/tum-kampanyalar', wait_until='networkidle')
        
        print("API requests made:")
        for url in apis:
            if 'api' in url.lower() or 'json' in url.lower() or 'graphql' in url.lower() or 'campaign' in url.lower() or 'pokus.com.tr' in url:
                print(url)
                
        html = await page.content()
        from bs4 import BeautifulSoup
        soup = BeautifulSoup(html, 'html.parser')
        links = soup.find_all('a')
        
        print("\nAll links on page:")
        camp_links = set(a['href'] for a in links if 'href' in a.attrs)
        for l in camp_links:
            if l.startswith('/'):
                print('Link:', l)
        
        await browser.close()

if __name__ == "__main__":
    asyncio.run(main())
