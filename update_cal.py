import os
import json
import hashlib
import requests
import time
from bs4 import BeautifulSoup
from google import genai
from google.genai import errors

# --- KONFIGURATION ---
SERPER_KEY = os.getenv("SERPER_API_KEY")
GEMINI_KEY = os.getenv("GEMINI_API_KEY")
DATABASE_FILE = "data.json"
ICS_FILE = "events.ics"

# Wir nutzen das Modell, das bei dir gerade erfolgreich war
TARGET_MODEL = "models/gemini-2.5-flash"

client = genai.Client(api_key=GEMINI_KEY) if GEMINI_KEY else None

def load_db():
    if os.path.exists(DATABASE_FILE):
        with open(DATABASE_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    return {"events": {}}

def save_db(db):
    with open(DATABASE_FILE, "w", encoding="utf-8") as f:
        json.dump(db, f, indent=2, ensure_ascii=False)

def get_page_content(url):
    try:
        headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'}
        response = requests.get(url, headers=headers, timeout=10)
        soup = BeautifulSoup(response.text, 'html.parser')
        for s in soup(["script", "style", "nav", "footer"]): s.extract()
        return soup.get_text()[:5000] # Genug Kontext für die KI
    except:
        return ""

def extract_details_with_ai(text, source_url):
    prompt = (
        f"Extrahiere Event-Details für das Jahr 2026 als JSON. "
        f"Felder: summary, start (YYYYMMDD), end (YYYYMMDD), location, type, description. "
        f"Quelle: {source_url}. Text: {text}"
    )
    try:
        response = client.models.generate_content(
            model=TARGET_MODEL,
            contents=prompt,
            config={'response_mime_type': 'application/json'}
        )
        return json.loads(response.text)
    except Exception as e:
        if "429" in str(e): return "STOP"
        print(f"  ! KI-Fehler: {e}")
        return None

def generate_ics(events_dict):
    ics = ["BEGIN:VCALENDAR", "VERSION:2.0", "PRODID:-//EventBot//DE", "METHOD:PUBLISH"]
    for eid, e in events_dict.items():
        if e.get("status") == "active":
            ics.extend([
                "BEGIN:VEVENT",
                f"UID:{eid}",
                f"SUMMARY:[{e.get('type','EVENT').upper()}] {e['summary']}",
                f"DTSTART;VALUE=DATE:{e['start']}",
                f"DTEND;VALUE=DATE:{e['end']}",
                f"LOCATION:{e['location']}",
                f"DESCRIPTION:{e.get('description','')} Link: {e.get('link','')}",
                "END:VEVENT"
            ])
    ics.append("END:VCALENDAR")
    with open(ICS_FILE, "w", encoding="utf-8") as f:
        f.write("\n".join(ics))

def main():
    db = load_db()
    queries = ["Service Design Konferenz 2026", "UX Design Events 2026", "Innovation Public Sector 2026"]
    
    for query in queries:
        print(f"\n>>> Suche: {query}")
        try:
            res = requests.post("https://google.serper.dev/search", 
                                headers={'X-API-KEY': SERPER_KEY},
                                json={"q": query, "num": 5}).json()
        except: continue
        
        for item in res.get('organic', []):
            link = item['link']
            link_id = hashlib.md5(link.encode()).hexdigest()
            
            if link_id in db["events"]: continue
            
            print(f"  * Scrape: {link}")
            content = get_page_content(link)
            if len(content) < 200: continue
            
            time.sleep(2) 
            details = extract_details_with_ai(content, link)
            
            if details == "STOP":
                print("!!! Quota erreicht. Speichere und beende.")
                save_db(db)
                generate_ics(db["events"])
                return

            # --- HIER IST DIE REPARATUR ---
            # Falls die KI eine Liste geschickt hat, nehmen wir das erste Element
            if isinstance(details, list) and len(details) > 0:
                details = details[0]
            
            # Jetzt prüfen wir, ob wir wirklich ein gültiges Objekt mit Startdatum haben
            if isinstance(details, dict) and details.get("start"):
                details["link"] = link
                details["status"] = "active"
                db["events"][link_id] = details
                print(f"    ✅ Gefunden: {details['summary']}")
                save_db(db)
            else:
                print(f"    ⚠️ Keine eindeutigen Event-Daten gefunden auf {link}")
                db["events"][link_id] = {"status": "ignored"}
                save_db(db)

    generate_ics(db["events"])
    print("\n>>> Fertig! Kalender aktualisiert.")

if __name__ == "__main__":
    main()
