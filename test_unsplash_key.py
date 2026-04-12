import requests
import sys

keys_to_test = [
    "LiTA57Sog1Av5BZTzW8rDrZz576OflmvMoFaVh50_kc",
    "LiTA57SogiAv5BZTzW8rDrZz576OflmvMoFaVh50_kc",
    "LiTA57SogIAv5BZTzW8rDrZz576OflmvMoFaVh50_kc"
]

for key in keys_to_test:
    res = requests.get("https://api.unsplash.com/photos/random", params={"query": "finance", "client_id": key})
    if res.status_code == 200:
        print(f"SUCCESS with key: {key}")
        sys.exit(0)
    else:
        print(f"FAILED with key: {key} - Status: {res.status_code}")
