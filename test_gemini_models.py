import os
from google import genai
from dotenv import load_dotenv

load_dotenv()

api_key = os.environ.get("GEMINI_API_KEY")
client = genai.Client(api_key=api_key)

models_to_try = [
    "gemini-1.5-flash",
    "gemini-1.5-flash-latest",
    "gemini-1.5-flash-002",
    "gemini-2.0-flash-exp",
    "gemini-3.1-flash-lite-preview"
]

for model in models_to_try:
    try:
        response = client.models.generate_content(
            model=model,
            contents="hi"
        )
        print(f"✅ {model} works!")
    except Exception as e:
        print(f"❌ {model} failed")
