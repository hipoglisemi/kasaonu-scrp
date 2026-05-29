import os
import re
from urllib.parse import urlparse
import psycopg2
from dotenv import load_dotenv

# Load local environment variables from .env
load_dotenv()

# We connect to the local forwarded port 5434
# DATABASE_URL = "postgres://postgres:****@localhost:5434/postgres"
db_url = os.getenv("DATABASE_URL")
if not db_url:
    # Fallback to local tunnel connection
    db_url = "postgresql://postgres:postgres@localhost:5434/postgres"
else:
    # Ensure it points to localhost:5434 for local connection
    db_url = db_url.replace("localhost:5432", "localhost:5434")
    db_url = db_url.replace("127.0.0.1:5432", "127.0.0.1:5434")
    db_url = db_url.replace("46.225.74.97:5433", "localhost:5434")

print(f"Connecting to database...")

try:
    conn = psycopg2.connect(db_url)
    cur = conn.cursor()
    print("Successfully connected!")
except Exception as e:
    print(f"Connection failed: {e}")
    exit(1)

domains = set()

# Regex to match absolute http/https URLs
url_regex = re.compile(r'https?://[^\s\'"()<>\[\]]+')

def add_url(url):
    if not url or not isinstance(url, str):
        return
    url = url.strip()
    if not url.startswith('http'):
        return
    try:
        parsed = urlparse(url)
        if parsed.netloc:
            # Remove port if present
            hostname = parsed.hostname
            if hostname:
                domains.add(hostname.lower())
    except Exception:
        pass

def scan_text_for_urls(text):
    if not text or not isinstance(text, str):
        return
    matches = url_regex.findall(text)
    for match in matches:
        # Check if it looks like an image file or common image path
        lower_match = match.lower()
        if any(ext in lower_match for ext in ['.jpg', '.jpeg', '.png', '.gif', '.webp', '.svg', '/upload', '/media', '/getmedia', '/assets']):
            # Clean trailing punctuation
            clean_url = match
            while clean_url and clean_url[-1] in ['.', ',', ';', ')', ']', '"', "'"]:
                clean_url = clean_url[:-1]
            add_url(clean_url)

# 1. Scan campaigns
print("Scanning campaigns table...")
cur.execute("SELECT image_url, title, description FROM campaigns")
for row in cur.fetchall():
    add_url(row[0])
    scan_text_for_urls(row[1])
    scan_text_for_urls(row[2])

# 2. Scan blogs
print("Scanning blogs table...")
# Check if blogs table exists first
cur.execute("SELECT EXISTS (SELECT FROM information_schema.tables WHERE table_name = 'blogs')")
if cur.fetchone()[0]:
    # Let's inspect column names first
    cur.execute("SELECT column_name FROM information_schema.columns WHERE table_name = 'blogs'")
    cols = [r[0] for r in cur.fetchall()]
    print(f"Blogs table columns: {cols}")
    
    # We will query all text columns
    query_cols = [c for c in cols if c in ['image_url', 'cover_image', 'thumbnail', 'content', 'summary', 'title']]
    if query_cols:
        select_clause = ", ".join(query_cols)
        cur.execute(f"SELECT {select_clause} FROM blogs")
        for row in cur.fetchall():
            for val in row:
                if val:
                    if str(val).startswith('http'):
                        add_url(str(val))
                    else:
                        scan_text_for_urls(str(val))

# 3. Scan cards
print("Scanning cards table...")
cur.execute("SELECT logo_url, image_url FROM cards")
for row in cur.fetchall():
    add_url(row[0])
    add_url(row[1])

# 4. Scan banks
print("Scanning banks table...")
cur.execute("SELECT logo_url FROM banks")
for row in cur.fetchall():
    add_url(row[0])

# 5. Scan brands
print("Scanning brands table...")
cur.execute("SELECT logo_url FROM brands")
for row in cur.fetchall():
    add_url(row[0])

# 6. Scan card_details
print("Scanning card_details table...")
cur.execute("SELECT EXISTS (SELECT FROM information_schema.tables WHERE table_name = 'card_details')")
if cur.fetchone()[0]:
    cur.execute("SELECT column_name FROM information_schema.columns WHERE table_name = 'card_details'")
    cols = [r[0] for r in cur.fetchall()]
    image_cols = [c for c in cols if 'logo' in c or 'image' in c or 'icon' in c or 'url' in c]
    if image_cols:
        cur.execute(f"SELECT {', '.join(image_cols)} FROM card_details")
        for row in cur.fetchall():
            for val in row:
                if val and str(val).startswith('http'):
                    add_url(str(val))

print(f"\nScan completed! Found {len(domains)} unique domains:")
sorted_domains = sorted(list(domains))
for d in sorted_domains:
    print(f"  - {d}")

# Let's save them to a file for comparison
with open("scratch/scanned_domains.txt", "w") as f:
    for d in sorted_domains:
        f.write(d + "\n")

cur.close()
conn.close()
