import requests
import sys

key = "LITa57Sog1Av5BZTzW8rDrZz576OfLmvMdFaVh50_kc"
res = requests.get("https://api.unsplash.com/photos/random", params={"query": "finance", "client_id": key})

print(f"Status Code: {res.status_code}")
if res.status_code == 200:
    data = res.json()
    print("Success! Image URL:", data["urls"]["regular"])
    sys.exit(0)
else:
    print("Failed. Response:", res.text)
    sys.exit(1)
