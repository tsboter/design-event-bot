import os
from google import genai

GEMINI_KEY = os.getenv("GEMINI_API_KEY")

def simple_check():
    if not GEMINI_KEY:
        print("❌ Kein API_KEY gefunden!")
        return

    client = genai.Client(api_key=GEMINI_KEY)
    
    print("--- 🔍 LISTE DER MODELLE ---")
    try:
        # Wir listen einfach nur die Namen auf
        models = client.models.list()
        for m in models:
            print(f"Gefunden: {m.name}")
            
        print("\n--- 🚀 TEST MIT DEM ERSTEN MODELL ---")
        # Wir nehmen das erste Modell aus der Liste automatisch
        first_model = next(client.models.list()).name
        response = client.models.generate_content(
            model=first_model,
            contents="Antworte nur mit 'Bereit'."
        )
        print(f"✅ Erfolg mit {first_model}: {response.text}")
        
    except Exception as e:
        print(f"❌ Fehler: {e}")

if __name__ == "__main__":
    simple_check()
