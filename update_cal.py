import os
import json
import hashlib
import requests
import time
import random
from bs4 import BeautifulSoup
from google import genai

# --- KONFIGURATION ---
THEMEN = ["Service Design", "UX Design", "Public Sector Innovation", "Strategic Design"]

# Sprachen-Mapping für die Suche
SPRACH_MAPPING = {
    "de": {"ort": "Deutschland", "formate": ["Konferenz", "Workshop", "Meet-up"]},
    "en": {"ort": "Europe", "formate": ["Conference", "Workshop", "Summit", "Talk"]}
}

SEED_URLS = [
    "https://www.service-design-network.org/events",
    "https://uxpa.org/calendar/",
    "https://www.servicedesignglobalconference.com/",
    "https://uxconf.de/",
    "https://digitale-leute.de/summit/",
    "https://www.interaction26.org/"
]

# API-Einstellungen
SERPER_KEY = os.getenv("SERPER_API_KEY")
GEMINI_KEY = os.getenv("GEMINI_API_KEY")
DATABASE_FILE = "data.json"
ICS_FILE = "events.ics"
TARGET_MODEL = "models/gemini-2.5-flash"

client = genai.Client(api_key=GEMINI_KEY) if GEMINI_KEY else None

def load_db():
    """Lädt die Datenbank und entfernt ignorierte Einträge für einen frischen Versuch."""
    if os.path.exists(DATABASE_FILE):
        try:
            with open(DATABASE_FILE, "r", encoding="utf-8") as f:
                db = json.load(f)
                # Filter: Wir behalten nur die echten Events (status: active)
                # Damit bekommen 'ignored' Links beim nächsten Run eine neue Chance.
                active_events = {k: v for k, v in db.get("events", {}).items() if v.get("status") == "active"}
                return {"events": active_events}
        except:
            pass
    return {"events": {}}

def save_db(db):
    with open(DATABASE_FILE, "w", encoding="utf-8") as f:
        json.dump(db, f, indent=2, ensure_ascii=False)

def extract_details_with_ai(text, source_url):
    """KI-Prompt: Aggressiver auf Events programmiert."""
    prompt = (
        f"Search the text from {source_url} for professional Design, UX, or Service Design events in 2026. "
        f"Format as a JSON list: [{{summary, start(YYYYMMDD), end(YYYYMMDD), location, type, description}}]. "
        f"If the text contains any event information, extract it. If not, return an empty list []. "
        f"Text to analyze: {text}"
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

def process_url(link, db):
    """Verarbeitet eine einzelne URL."""
    link_id = hashlib.md5(link.encode()).hexdigest()
    if link_id in db["events"]:
        return False # Schon als aktives Event bekannt

    print(f"  * Scrape: {link}")
    try:
        headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'}
        response = requests.get(link, headers=headers, timeout=15)
        soup = BeautifulSoup(response.text, 'html.parser')
        # Wir entfernen unnötigen Ballast für die KI
        for s in soup(["script", "style", "nav", "footer", "header"]): s.decompose()
        content = soup.get_text()[:5000]
        
        time.sleep(2)
        found_events = extract_details_with_ai(content, link)
        
        new_added = False
        for event in found_events:
            if not event or not event.get("start") or not event.get("summary"):
                continue
            
            # Dubletten-Check innerhalb der aktiven Events
            is_dupe = any(e.get("summary") == event["summary"] and e.get("start") == event["start"] 
                         for e in db["events"].values())
            
            if not is_dupe:
                event["link"] = link
                event["status"] = "active"
                # Eindeutige ID für dieses spezifische Event
                event_uid = hashlib.md5((event["summary"] + event["start"]).encode()).hexdigest()
                db["events"][event_uid] = event
                print(f"    ✅ GEFUNDEN: {event['summary']} ({event['start']})")
                new_added = True
        return new_added
    except Exception as e:
        print(f"    ❌ Fehler: {e}")
        return False

def generate_ics(db):
    """Erstellt die ICS-Datei basierend auf allen aktiven Events."""
    ics = [
        "BEGIN:VCALENDAR",
        "VERSION:2.0",
        "PRODID:-//DesignBot//DE",
        "X-WR-CALNAME:Design Events Europe 2026",
        "X-WR-TIMEZONE:Europe/Berlin",
        "METHOD:PUBLISH"
    ]
    for eid, e in db["events"].items():
        if e.get("status") == "active":
            ics.extend([
                "BEGIN:VEVENT",
                f"UID:{eid}",
                f"SUMMARY:{e['summary']}",
                f"DTSTART;VALUE=DATE:{e['start']}",
                f"DTEND;VALUE=DATE:{e.get('end', e['start'])}",
                f"LOCATION:{e.get('location','Online/TBA')}",
                f"DESCRIPTION:Quelle: {e.get('link','')}\\n{e.get('description','')}",
                "END:VEVENT"
            ])
    ics.append("END:VCALENDAR")
    with open(ICS_FILE, "w", encoding="utf-8") as f:
        f.write("\n".join(ics))

def main():
    db = load_db()
    
    # 1. Seed-URLs
    print(">>> Prüfe Seed-Liste...")
    for url in SEED_URLS:
        process_url(url, db)
        save_db(db)

    # 2. Rotierende Suche (2 zufällige Sprachen pro Run)
    sprachen = list(SPRACH_MAPPING.keys())
    auswahl = random.sample(sprachen, 2)
    print(f"\n>>> Suche in Sprachen: {auswahl}")

    for lang in auswahl:
        conf = SPRACH_MAPPING[lang]
        for thema in THEMEN:
            query = f"{thema} {conf['formate'][0]} {conf['ort']} 2026"
            print(f"--- Query: {query} ---")
            try:
                r = requests.post("https://google.serper.dev/search", 
                                  headers={'X-API-KEY': SERPER_KEY},
                                  json={"q": query, "num": 8}).json()
                for item in r.get('organic', []):
                    process_url(item['link'], db)
                    save_db(db)
            except:
                continue

    generate_ics(db)
    print("\n>>> Fertig! events.ics wurde aktualisiert.")

if __name__ == "__main__":
    main()
