import asyncio
from playwright.async_api import async_playwright

async def get_img(page, url):
    await page.goto(url, wait_until='domcontentloaded')
    await page.wait_for_timeout(2000)
    image_url = await page.evaluate("""
        () => {
            const isUglyGuide = (img) => {
                const alt = (img.alt || '').toLowerCase();
                return alt.includes('çerez') || alt.includes('aksi durumda') || alt.includes('tıkla kazan butonuyla') || alt.includes('yönlendikten sonra');
            };

            const itemImgs = document.querySelectorAll('.item img.img-fluid');
            for (const img of itemImgs) {
                const src = img.src || '';
                if (src.includes('img-hopi.mncdn.com') && !src.includes('web-assets') && !src.includes('hopi-logo') && !isUglyGuide(img)) {
                    return src;
                }
            }
            const allImgs = document.querySelectorAll('img');
            for (const img of allImgs) {
                const src = img.src || '';
                const w = img.naturalWidth || img.width || 0;
                if (src.includes('img-hopi.mncdn.com') && !src.includes('web-assets') && !src.includes('Logosu') && w > 200 && !isUglyGuide(img)) {
                    return src;
                }
            }
            return null;
        }
    """)
    return image_url

async def main():
    async with async_playwright() as p:
        b = await p.chromium.launch()
        page = await b.new_page()
        
        url1 = 'https://hopi.com.tr/kampanya/15-000-tl-ve-uzerine-1-000-paracik-kazan/1647961'
        print(f"İşbir Yatak: {await get_img(page, url1)}")
        
        url2 = 'https://hopi.com.tr/kampanya/taze-cicek-alisveristen-once-tikla-1-5-paracik-kazan/1670659'
        print(f"Taze Çiçek: {await get_img(page, url2)}")
        
        await b.close()

asyncio.run(main())
