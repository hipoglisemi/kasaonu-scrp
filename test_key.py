import json
import os
from google.oauth2 import service_account
import google.auth.transport.requests

def test_token():
    key_raw = os.getenv("SEARCH_CONSOLE_KEY")
    if not key_raw:
        print("SEARCH_CONSOLE_KEY environment variable not set.")
        return

    try:
        info = json.loads(key_raw)
        print(f"Testing key for: {info.get('client_email')}")
        
        scopes = ["https://www.googleapis.com/auth/webmasters.readonly"]
        credentials = service_account.Credentials.from_service_account_info(info, scopes=scopes)
        request = google.auth.transport.requests.Request()
        credentials.refresh(request)
        print("✅ Token refresh successful!")
        print(f"Token: {credentials.token[:10]}...")
    except Exception as e:
        print(f"❌ Token refresh failed: {e}")

if __name__ == "__main__":
    test_token()
