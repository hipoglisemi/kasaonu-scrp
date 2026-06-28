import os
from dotenv import load_dotenv
from google.genai import Client

# Load environment variables
load_dotenv('.env')
api_key = os.getenv('GEMINI_API_KEY')

if not api_key:
    print("API Key not found in .env")
    exit(1)

client = Client(api_key=api_key)

try:
    response = client.models.generate_content(
        model='gemini-1.5-flash',
        contents='Hello, testing 1.5 flash.'
    )
    print("SUCCESS!")
    print(f"Response: {response.text}")
except Exception as e:
    print(f"ERROR: {e}")
