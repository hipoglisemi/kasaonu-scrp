import requests

def test_api():
    headers = {
        "user-agent": "Dart/3.12 (dart:io)",
        "platform": "1",
        "content-type": "application/json"
    }
    # Let's try calling a public endpoint without auth, maybe we don't need it?
    # Or maybe there's a token endpoint?
    try:
        r = requests.post("https://prodapi.oliz.com.tr/api/guest/token", headers=headers, json={}, timeout=10, verify=False)
        print("Guest token endpoint:", r.status_code, r.text)
    except Exception as e:
        print("Guest error:", e)

    try:
        r = requests.post("https://prodapi.oliz.com.tr/api/device/init", headers=headers, json={"deviceId": "1234567890"}, timeout=10, verify=False)
        print("Device init:", r.status_code, r.text)
    except Exception as e:
        print("Device init error:", e)

    try:
        r = requests.post("https://prodapi.oliz.com.tr/api/member/promotions", headers=headers, json={"keyword":"","brandIds":[],"categoryIds":[]}, timeout=10, verify=False)
        print("Promotions without auth:", r.status_code, r.text)
    except Exception as e:
        print("Promotions error:", e)

test_api()
