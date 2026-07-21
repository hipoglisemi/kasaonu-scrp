import requests
import urllib3
urllib3.disable_warnings()

headers = {
    "user-agent": "Dart/3.12 (dart:io)",
    "platform": "1",
    "content-type": "application/json"
}

url_init = "https://prodapi.oliz.com.tr/api/users/init"
r_init = requests.get(url_init, headers=headers, verify=False)
guest_token = r_init.json().get("payload", {}).get("guest_token")
headers["guest-token"] = guest_token

url_auth = "https://prodapi.oliz.com.tr/api/users/authenticate"
r_auth = requests.post(url_auth, headers=headers, json={"email": "test@test.com", "password": "password123"}, verify=False)
print("Auth Status:", r_auth.status_code)
print("Auth Response:", r_auth.text[:200])

