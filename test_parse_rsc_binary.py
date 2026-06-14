import re
import json
import codecs

with open('detail_test.html', 'rb') as f:
    html_content = f.read()

# Find all self.__next_f.push( [ ... , "..." ] )
# We can use binary regex
pushes = re.findall(b'self\\.__next_f\\.push\\(\\[\\s*\\d+\\s*,\\s*"(.*?)"\\s*\\]\\)', html_content)
if not pushes:
    pushes = re.findall(b"self\\.__next_f\\.push\\(\\[\\s*\\d+\\s*,\\s*'(.*?)'\\s*\\]\\)", html_content)

full_payload_bytes = b""
for push in pushes:
    # Decode escape sequences like \n, \", \\, \u0080 in bytes
    try:
        # codecs.escape_decode unescapes backslashes in bytes
        decoded_bytes, _ = codecs.escape_decode(push)
        full_payload_bytes += decoded_bytes
    except Exception as e:
        print("Decode error:", e)

# Now decode the entire accumulated bytes as UTF-8!
full_payload = full_payload_bytes.decode('utf-8', errors='ignore')
print("Length of payload:", len(full_payload))

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
else:
    print("No query match found.")
