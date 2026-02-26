import os
import json
import hashlib
import requests
import time
from bs4 import BeautifulSoup
from google import genai

# --- ANPASSBARE KONFIGURATION ---
THEMEN = ["Service Design", "UX Design", "Public Sector Innovation"]
FORMATE = ["Konferenz", "Workshop", "Meet-up", "Talk"]
ORTE = ["Berlin", "Deutschland", "Europa", "Online"]

# SEED-LISTE: Diese URLs werden IMMER geprüft
SEED_URLS = [
    "https://www.service-design-network.org/events",
    "https://interaction-design.org/events",
    "https://uxpa.org/calendar/",
    "https://www.ux-berlin.com/",
    "https://www.servicedesignglobalconference.com/",
    "https://uxconf.de/",
    "https://www.interaction26.org/",
    "https://digitale-leute.de/summit/",
    "https://www.euroia.org/"
]

# API-Einstellungen
SERPER_KEY = os.getenv("SERPER_API_KEY")
GEMINI_KEY = os.getenv("GEMINI_API_KEY")
DATABASE_FILE = "data.json"
ICS_FILE = "events.ics"
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

def process_url(link, db):
    """Scraped eine URL und füttert die KI."""
    link_id = hashlib.md5(link.encode()).hexdigest()
    if link_id in db["events"]: 
        return False # Schon bekannt

    print(f"  * Analysiere: {link}")
    try:
        headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'}
        page = requests.get(link, headers=headers, timeout=15).text
        content = BeautifulSoup(page, 'html.parser').get_text()[:5000]
        
        time.sleep(2)
        found_events = extract_details_with_ai(content, link)
        
        new_found = False
        for event in found_events:
            if not event or not event.get("start") or not event.get("summary"):
                continue
            
            # Inhalts-Check (Titel + Datum)
            is_dupe = False
            for eid, e in db["events"].items():
                if e.get("summary") == event["summary"] and e.get("start") == event["start"]:
                    is_dupe = True
                    break
            
            if not is_dupe:
                event["link"] = link
                event["status"] = "active"
                db["events"][link_id + "_" + str(time.time())] = event
                print(f"    ✅ NEU: {event['summary']}")
                new_found = True
        
        if not found_events:
            db["events"][link_id] = {"status": "ignored"}
            
        return new_found
    except Exception as e:
        print(f"    ❌ Fehler bei {link}: {e}")
        return False

def extract_details_with_ai(text, source_url):
    prompt = (
        f"Extrahiere Events für 2026 (Formate: {', '.join(FORMATE)}). "
        f"Fokus auf Regionen: {', '.join(ORTE)}. "
        f"Antworte NUR als JSON-Liste: [{{summary, start(YYYYMMDD), end, location, type, description}}]. "
        f"Quelle: {source_url}. Text: {text}"
    )
    try:
        response = client.models.generate_content(
            model=TARGET_MODEL,
            contents=prompt,
            config={'response_mime_type': 'application/json'}
        )
        data = json.loads(response.text)
        return data if isinstance(data, list) else [data]
    except:
        return []

def generate_ics(db):
    ics = ["BEGIN:VCALENDAR", "VERSION:2.0", "PRODID:-//DesignBot//DE", "X-WR-CALNAME:Design Events 2026", "METHOD:PUBLISH"]
    for eid, e in db["events"].items():
        if e.get("status") == "active":
            ics.extend([
                "BEGIN:VEVENT",
                f"UID:{eid}",
                f"SUMMARY:{e['summary']}",
                f"DTSTART;VALUE=DATE:{e['start']}",
                f"DTEND;VALUE=DATE:{e.get('end', e['start'])}",
                f"LOCATION:{e.get('location','Berlin/Online')}",
                f"DESCRIPTION:Link: {e.get('link','')}",
                "END:VEVENT"
            ])
    ics.append("END:VCALENDAR")
    with open(ICS_FILE, "w", encoding="utf-8") as f:
        f.write("\n".join(ics))

def main():
    db = load_db()
    
    # 1. Zuerst die Seed-Liste abarbeiten
    print(">>> Verarbeite Seed-Liste...")
    for url in SEED_URLS:
        process_url(url, db)
        save_db(db)

    # 2. Dann die Google-Suche
    print("\n>>> Starte Google-Suche...")
    for thema in THEMEN:
        for ort in ORTE[:2]: # Nur Berlin & Deutschland für die Suche
            query = f"{thema} Event {ort} 2026"
            try:
                res = requests.post("https://google.serper.dev/search", 
                                    headers={'X-API-KEY': SERPER_KEY},
                                    json={"q": query, "num": 5}).json()
                for item in res.get('organic', []):
                    process_url(item['link'], db)
                    save_db(db)
            except: continue

    generate_ics(db)
    print("\n>>> Kalender aktualisiert!")

if __name__ == "__main__":
    main()
