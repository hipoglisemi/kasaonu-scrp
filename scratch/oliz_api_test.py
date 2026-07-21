import requests
import urllib3
urllib3.disable_warnings()

headers = {
    "user-agent": "Dart/3.12 (dart:io)",
    "guest-token": "133b3bcf-9db4-46c5-a745-8edafba9e70d",
    "platform": "1",
    "content-type": "application/json"
}

ep2 = "/api/guest/promotions"
url2 = f"https://prodapi.oliz.com.tr{ep2}"
r2 = requests.post(url2, headers=headers, json={"keyword":"","brandIds":[],"categoryIds":[]}, verify=False)
print("Guest promotions - Status:", r2.status_code)
if r2.status_code == 200:
    print(len(r2.json().get("payload", {}).get("campaigns", [])))
