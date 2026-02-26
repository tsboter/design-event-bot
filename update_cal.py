import os
import json
import hashlib
import requests
from bs4 import BeautifulSoup
from google import genai

# Konfiguration
GEMINI_KEY = os.getenv("GEMINI_API_KEY")
SERPER_KEY = os.getenv("SERPER_API_KEY")

# Wir nutzen das stabilste Modell überhaupt
MODEL_NAME = "gemini-1.5-flash" 

def test_ki():
    if not GEMINI_KEY:
        print("❌ FEHLER: Kein GEMINI_API_KEY gefunden!")
        return False
    
    client = genai.Client(api_key=GEMINI_KEY)
    try:
        # Ein ganz einfacher Test-Prompt
        response = client.models.generate_content(
            model=MODEL_NAME,
            contents="Hallo, antwortet dir eine KI? Antworte nur mit JA."
        )
        print(f"✅ KI-Test erfolgreich: {response.text}")
        return True
    except Exception as e:
        print(f"❌ KI-Test fehlgeschlagen: {e}")
        return False

def main():
    print(">>> Starte System-Check...")
    if test_ki():
        print(">>> API Key funktioniert! Starte jetzt die Suche...")
        # Hier würde dein eigentlicher Scraper-Code folgen
    else:
        print(">>> Abbruch: API Key immer noch nicht bereit.")

if __name__ == "__main__":
    main()
