import os
from google import genai
from dotenv import load_dotenv

# Load env
load_dotenv(override=True)

def list_models_for_keys():
    # Find all GEMINI_API_KEY_X in env
    all_env_keys = [k for k in os.environ.keys() if k.startswith("GEMINI_API_KEY")]
    
    # Sort keys for stable order
    def sort_key(k):
        if k == "GEMINI_API_KEY": return 0
        try: return int(k.split("_")[-1])
        except: return 999
    
    sorted_env_keys = sorted(all_env_keys, key=sort_key)
    
    for env_name in sorted_env_keys:
        key = os.environ.get(env_name)
        if not key: continue
        
        print(f"\n🔑 Checking Key: {env_name} ({key[:10]}...)")
        try:
            client = genai.Client(api_key=key)
            models = client.models.list()
            supported = []
            for m in models:
                # We are interested in gemini models
                if "gemini" in m.name:
                    supported.append(m.name)
            
            if supported:
                print(f"✅ Supported Gemini Models: {', '.join(supported)}")
            else:
                print("⚠️ No Gemini models found for this key.")
                
        except Exception as e:
            print(f"❌ Error checking key {env_name}: {e}")

if __name__ == "__main__":
    list_models_for_keys()
