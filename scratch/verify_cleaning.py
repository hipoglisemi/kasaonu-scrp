
import os
import sys

# Fix sys.path to include project root
project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if project_root not in sys.path:
    sys.path.insert(0, project_root)

from src.services.text_cleaner import clean_campaign_text

# Mock HTML content representing an Isbankasi page with navigation noise
MOCK_HTML = """
<html>
<body>
    <nav class="main-nav">
        <ul>
            <li>Şubeler</li>
            <li>İletişim</li>
            <li>Maximum Kart Al</li>
            <li>Maximiles Dünyası</li>
        </ul>
    </nav>
    
    <div class="campaign-detail">
        <h1>Samsung Galaxy S24 Kampanyası</h1>
        <p>Samsung.com'da anında indirim fırsatı.</p>
        <div class="terms">
            Kampanya 1-31 Mart arasında geçerlidir.
        </div>
    </div>
    
    <footer class="site-footer">
        <p>Bizi Takip Edin</p>
        <p>Copyright 2026</p>
    </footer>
</body>
</html>
"""

def test():
    print("--- Testing Hardened Cleaner ---")
    title = "Samsung Galaxy S24 Kampanyası"
    
    # Test 1: Full HTML
    cleaned = clean_campaign_text(MOCK_HTML, title=title)
    print("CLEANED OUTPUT:")
    print("-" * 30)
    print(cleaned)
    print("-" * 30)
    
    # Checks
    noise_words = ["Şubeler", "İletişim", "Maximum Kart Al", "Bizi Takip Edin"]
    found_noise = [w for w in noise_words if w in cleaned]
    
    if not found_noise:
        print("✅ SUCCESS: All navigation noise removed!")
    else:
        print(f"❌ FAIL: Found noise: {found_noise}")
        
    if "Samsung Galaxy S24 Kampanyası" in cleaned:
        print("✅ SUCCESS: Campaign content preserved!")
    else:
        print("❌ FAIL: Campaign content lost!")

if __name__ == "__main__":
    test()
