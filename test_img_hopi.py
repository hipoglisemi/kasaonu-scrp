import asyncio
from playwright.async_api import async_playwright

async def main():
    async with async_playwright() as p:
        b = await p.chromium.launch()
        page = await b.new_page()
        await page.goto('https://hopi.com.tr/kampanya/dugun-alisverisinde-1-250-paracik-kazan/1677356', wait_until='domcontentloaded')
        await page.wait_for_timeout(2000)
        image_url = await page.evaluate("""
            () => {
                const itemImgs = document.querySelectorAll('.item img.img-fluid');
                for (const img of itemImgs) {
                    const src = img.src || '';
                    const w = img.naturalWidth || img.width || 0;
                    const h = img.naturalHeight || img.height || 0;
                    if (src.includes('img-hopi.mncdn.com') && !src.includes('web-assets') && !src.includes('hopi-logo') && (w * 1.3 > h) && w > 0) {
                        return src;
                    }
                }
                const allImgs = document.querySelectorAll('img');
                for (const img of allImgs) {
                    const src = img.src || '';
                    const w = img.naturalWidth || img.width || 0;
                    const h = img.naturalHeight || img.height || 0;
                    if (src.includes('img-hopi.mncdn.com') && !src.includes('web-assets') && !src.includes('Logosu') && (w * 1.3 > h) && w > 200) {
                        return src;
                    }
                }
                return null;
            }
        """)
        print(f"Extracted Image: {image_url}")
        await b.close()

asyncio.run(main())
