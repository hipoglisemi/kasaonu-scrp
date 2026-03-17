import json
import os
from google.oauth2 import service_account
from googleapiclient.discovery import build

def list_sites():
    key_raw = os.getenv("SEARCH_CONSOLE_KEY")
    if not key_raw:
        print("SEARCH_CONSOLE_KEY environment variable not set.")
        return

    try:
        info = json.loads(key_raw)
        credentials = service_account.Credentials.from_service_account_info(
            info, 
            scopes=["https://www.googleapis.com/auth/webmasters.readonly"]
        )
        service = build("searchconsole", "v1", credentials=credentials)
        
        sites = service.sites().list().execute()
        print("Connected sites:")
        for site in sites.get('siteEntry', []):
            print(f"- {site['siteUrl']} (Permission: {site['permissionLevel']})")
            
    except Exception as e:
        print(f"Error listing sites: {e}")

if __name__ == "__main__":
    list_sites()
