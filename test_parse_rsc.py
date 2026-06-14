import re
import json

with open('detail_test.html', 'r', encoding='utf-8') as f:
    html_content = f.read()

# Find all __next_f.push calls
pushes = re.findall(r'self\.__next_f\.push\(\[\s*\d+\s*,\s*"(.*?)"\s*\]\)', html_content)
if not pushes:
    # Try with single quotes
    pushes = re.findall(r"self\.__next_f\.push\(\[\s*\d+\s*,\s*'(.*?)'\s*\]\)", html_content)

full_payload = ""
for push in pushes:
    # Unescape the string content
    # In JS push strings, they escape double quotes as \" and backslashes as \\
    # We can decode this string using codecs
    try:
        decoded = bytes(push, "utf-8").decode("unicode_escape")
        full_payload += decoded
    except Exception as e:
        print("Decode error:", e)
        # Fallback to simple replace
        decoded = push.replace('\\"', '"').replace('\\\\', '\\')
        full_payload += decoded

# Now look for "queries" in the full payload
print("Length of unescaped payload:", len(full_payload))

# Find the campaign data JSON
# It's inside a react query state: "queries":[{"dehydratedAt":..., "state":{"data":{...}}}]
query_match = re.search(r'"queries"\s*:\s*(\[.*?\])\s*\}', full_payload)
if query_match:
    try:
        queries_json = json.loads(query_match.group(1))
        for query in queries_json:
            if "state" in query and "data" in query["state"]:
                campaign_data = query["state"]["data"]
                print("SUCCESSFULLY PARSED DATA:")
                print(json.dumps(campaign_data, indent=2, ensure_ascii=False))
    except Exception as e:
        print("Failed to parse JSON:", e)
        # Let's print a snippet
        print(full_payload[full_payload.find('"queries"'):full_payload.find('"queries"') + 500])
else:
    print("No query match found.")
