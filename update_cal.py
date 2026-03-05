import os
import json
import hashlib
import requests
import time
import random
import re
from bs4 import BeautifulSoup
from google import genai

# --- KONFIGURATION ---
THEMEN = ["Service Design", "UX Design", "Public Sector Innovation", "Strategic Design"]
SPRACH_MAPPING = {
    "de": {"ort": "Deutschland", "formate": ["Konferenz", "Workshop", "Meet-up"]},
    "en": {"ort": "Europe", "formate": ["Conference", "Workshop", "Summit", "Talk"]}
}

SEED_URLS = [
    "https://www.service-design-network.org/events",
    "https://uxpa.org/calendar/",
    "https://www.servicedesignglobalconference.com/",
    "https://uxconf.de/"
]

DATABASE_FILE = "data.json"
ICS_FILE = "events.ics"
TARGET_MODEL = "models/gemini-2.5-flash"

client = genai.Client(api_key=os.getenv("GEMINI_API_KEY"))

def load_db():
    if os.path.exists(DATABASE_FILE):
        with open(DATABASE_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    return {"events": {}}

def save_db(db):
    with open(DATABASE_FILE, "w", encoding="utf-8") as f:
        json.dump(db, f, indent=2, ensure_ascii=False)

def clean_string(text):
    return re.sub(r'[^a-z0-9]', '', text.lower())

def extract_details_with_ai(text, source_url):
    """Extrahiert Events und markiert vage Daten als Platzhalter."""
    prompt = (
        f"Analyze the text for professional Design/UX events in 2026. "
        f"RULES:\n"
        f"1. If a SPECIFIC DAY is found, provide it (YYYYMMDD) and set 'is_confirmed_date': true.\n"
        f"2. If ONLY A MONTH is found, use the 1st (YYYYMM01) and set 'is_confirmed_date': false.\n"
        f"3. If only '2026' is found without a month, ignore the event.\n"
        f"4. Format 'description' field:\n"
        f"Link: {source_url}\n"
        f"Format: [Typ]\n"
        f"Inhalt/Relevanz: [Max 2 Sätze]\n"
        f"5. Output as JSON list: [{{summary, start(YYYYMMDD), end(YYYYMMDD), is_confirmed_date, location, type, description}}].\n"
        f"Text: {text}"
    )
    try:
        response = client.models.generate_content(model=TARGET_MODEL, contents=prompt, config={'response_mime_type': 'application/json'})
        data = json.loads(response.text)
        return data if isinstance(data, list) else [data]
    except:
        return []

def process_url(link, db):
    link_id = hashlib.md5(link.encode()).hexdigest()
    # Wir lassen die Prüfung auf existierende Links hier zu, 
    # damit wir on_hold Events später updaten können, falls wir sie erneut scrapen.
    
    print(f"  * Analysiere: {link}")
    try:
        headers = {'User-Agent': 'Mozilla/5.0'}
        response = requests.get(link, headers=headers, timeout=15)
        soup = BeautifulSoup(response.text, 'html.parser')
        for s in soup(["script", "style", "nav", "footer", "header"]): s.decompose()
        content = soup.get_text()[:6000]
        
        time.sleep(2)
        found_events = extract_details_with_ai(content, link)
        
        for event in found_events:
            if not event or not event.get("start"): continue
            
            # Status-Logik: Nur Events mit bestätigtem Tag sind "active"
            if event.get("is_confirmed_date") is True:
                event["status"] = "active"
            else:
                event["status"] = "on_hold"
                print(f"    ⏳ Warteschlange (kein Tag): {event['summary']}")

            uid = hashlib.md5((event["summary"] + event["start"]).encode()).hexdigest()
            
            # Falls das Event schon existiert, aber jetzt ein "active" Datum hat -> Updaten
            if uid in db["events"] and db["events"][uid]["status"] == "active":
                continue
                
            db["events"][uid] = event
            if event["status"] == "active":
                print(f"    ✅ AKTIV: {event['summary']} ({event['start']})")
        return True
    except:
        return False

def generate_ics(db):
    """Erstellt die ICS-Datei NUR aus aktiven Events."""
    ics = [
        "BEGIN:VCALENDAR", "VERSION:2.0", "PRODID:-//DesignBot//DE", 
        "X-WR-CALNAME:Design Events 2026", "METHOD:PUBLISH"
    ]
    
    active_count = 0
    for eid, e in db["events"].items():
        # FILTER: Nur Events mit konkretem Tag landen im Kalender
        if e.get("status") == "active":
            desc = e.get('description', '').replace('\n', '\\n')
            ics.extend([
                "BEGIN:VEVENT",
                f"UID:{eid}",
                f"SUMMARY:{e['summary']}",
                f"DTSTART;VALUE=DATE:{e['start']}",
                f"DTEND;VALUE=DATE:{e.get('end', e['start'])}",
                f"LOCATION:{e.get('location', 'TBA')}",
                f"DESCRIPTION:{desc}",
                "END:VEVENT"
            ])
            active_count += 1
            
    ics.append("END:VCALENDAR")
    with open(ICS_FILE, "w", encoding="utf-8") as f:
        f.write("\n".join(ics))
    print(f">>> ICS erstellt mit {active_count} bestätigten Terminen.")

def main():
    db = load_db()
    
    # 1. Seeds
    for url in SEED_URLS: process_url(url, db)
    save_db(db)

    # 2. Suche
    for lang, conf in SPRACH_MAPPING.items():
        for thema in THEMEN:
            query = f"{thema} {conf['formate'][0]} {conf['ort']} 2026"
            try:
                r = requests.post("https://google.serper.dev/search", 
                                  headers={'X-API-KEY': os.getenv("SERPER_API_KEY")}, 
                                  json={"q": query, "num": 5}).json()
                for item in r.get('organic', []):
                    process_url(item['link'], db)
                    save_db(db)
            except: continue

    generate_ics(db)

if __name__ == "__main__":
    main()
