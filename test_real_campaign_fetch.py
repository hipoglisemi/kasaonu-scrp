import requests
import re
import json
import codecs

url = "https://tkpay.com/tr/campaign/milessmiles6tl1mil"
headers = {
    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
}

response = requests.get(url, headers=headers, timeout=30)
html_content = response.content

# Find all self.__next_f.push( [ ... , "..." ] )
pushes = re.findall(b'self\\.__next_f\\.push\\(\\[\\s*\\d+\\s*,\\s*"(.*?)"\\s*\\]\\)', html_content)
if not pushes:
    pushes = re.findall(b"self\\.__next_f\\.push\\(\\[\\s*\\d+\\s*,\\s*'(.*?)'\\s*\\]\\)", html_content)

full_payload_bytes = b""
for push in pushes:
    try:
        decoded_bytes, _ = codecs.escape_decode(push)
        full_payload_bytes += decoded_bytes
    except Exception as e:
        pass

full_payload = full_payload_bytes.decode('utf-8', errors='ignore')

query_match = re.search(r'"queries"\s*:\s*(\[.*?\])\s*\}', full_payload)
if query_match:
    try:
        queries_json = json.loads(query_match.group(1))
        for query in queries_json:
            if "state" in query and "data" in query["state"]:
                campaign_data = query["state"]["data"]
                print("Name:", campaign_data.get("name"))
                print("Desc:", campaign_data.get("description"))
                print("Rules:", campaign_data.get("rules"))
                print("Image:", campaign_data.get("webDetailImagePath"))
                print("EndDate:", campaign_data.get("endDate"))
    except Exception as e:
        print("JSON parse error:", e)
else:
    print("No query match found.")
