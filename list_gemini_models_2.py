import os
from dotenv import load_dotenv
from google.genai import Client

load_dotenv('.env')
api_key = os.getenv('GEMINI_API_KEY')

client = Client(api_key=api_key)

try:
    models = client.models.list()
    for m in models:
        print(f"Model: {m.name}")
except Exception as e:
    print(e)
