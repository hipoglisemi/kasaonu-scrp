import re
import json

with open('tkpay_index.html', 'r', encoding='utf-8') as f:
    content = f.read()

# Look for campaign slugs or urls in the RSC payload
# Often they look like "slug":"some-campaign" or just href=\"/tr/kampanya/...\"
links = re.findall(r'href=[\'\\"]([^\'\\"]*kampanya[^\'\\"]*)[\'\\"]', content, re.IGNORECASE)
print("Found links with 'kampanya':", set(links))

# Also let's check if the campaigns are just listed as strings
slugs = re.findall(r'kampanya/([\w-]+)', content)
print("Found slugs:", set(slugs))
