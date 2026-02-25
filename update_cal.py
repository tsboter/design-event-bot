import os
import json
import hashlib
import requests
from bs4 import BeautifulSoup
import google.generativeai as genai

# API Keys aus GitHub Secrets
SERPER_KEY = os.getenv("SERPER_API_KEY")
GEMINI_KEY = os.getenv("GEMINI_API_KEY")

genai.configure(api_key=GEMINI_KEY)
model = genai.GenerativeModel('gemini-1.5-flash')

def get_page_content(url):
    try:
        response = requests.get(url, timeout=10)
        soup = BeautifulSoup(response.text, 'html.parser')
        # Wir nehmen nur den Text, um Token zu sparen
        return soup.get_text()[:5000] 
    except:
        return ""

def extract_details_with_ai(page_text):
    prompt = f"""
    Extrahiere aus folgendem Text die Event-Details für 2026. 
    Antworte NUR im JSON-Format:
    {{
      "summary": "Name des Events",
      "start": "YYYYMMDD",
      "end": "YYYYMMDD",
      "location": "Stadt, Adresse",
      "description": "Kurze Info"
    }}
    Wenn kein Datum für 2026 gefunden wird, antworte mit "null".
    Text: {page_text}
    """
    try:
        response = model.generate_content(prompt)
        # Säubern der Antwort von Markdown-Code-Blöcken
        clean_json = response.text.replace("```json", "").replace("```", "").strip()
        return json.loads(clean_json)
    except:
        return None

def main():
    # ... (Such-Logik wie vorher) ...
    # Wenn ein interessanter Link gefunden wurde:
    
    print(f"Besuche: {url}")
    raw_text = get_page_content(url)
    event_details = extract_details_with_ai(raw_text)
    
    if event_details:
        # Hier in data.json speichern (Logik wie gehabt)
        print(f"Erfolgreich extrahiert: {event_details['summary']}")
