import os
import json
import hashlib
import requests
import time
import random
import re
from bs4 import BeautifulSoup
from google import genai

# --- DEINE NEUE KONFIGURATION ---
THEMEN = ["Service Design", "UX Design", "Public Sector Innovation", "Strategic Design"]

SPRACH_MAPPING = {
    "de": {"ort": "Deutschland", "formate": ["Konferenz", "Workshop", "Meet-up"]},
    "en": {"ort": "Europe", "formate": ["Conference", "Workshop", "Summit", "Talk"]}
}

SEED_URLS = [
    "https://www.service-design-network.org/events",
    "https://uxpa.org/calendar/",
    "https://www.servicedesignglobalconference.com/",
    "https://uxconf.de/",
    "https://www.interaction26.org/",
    "https://digitale-leute.de/summit/"
]

DATABASE_FILE = "data.json"
ICS_FILE = "events.ics"
TARGET_MODEL = "models/gemini-2.5-flash"

client = genai.Client(api_key=os.getenv("GEMINI_API_KEY"))

def load_db():
    if os.path.exists(DATABASE_FILE):
        with open(DATABASE_FILE, "r", encoding="utf-8") as f:
            db = json.load(f)
            # Nur aktive Events behalten
            db["events"] = {k: v for k, v in db.get("events", {}).items() if v.get("status") == "active"}
            return db
    return {"events": {}}

def save_db(db):
    with open(DATABASE_FILE, "w", encoding="utf-8") as f:
        json.dump(db, f, indent=2, ensure_ascii=False)

def clean_string(text):
    return re.sub(r'[^a-z0-9]', '', text.lower())

def is_duplicate(new_event, db):
    new_title = clean_string(new_event.get("summary", ""))
    new_date = new_event.get("start", "")
    for e in db["events"].values():
        if clean_string(e.get("summary", "")) == new_title and e.get("start") == new_date:
            return True
    return False

def extract_details_with_ai(text, source_url):
    prompt = (
        f"Analyze the text for professional Design/UX events in 2026. "
        f"RULES:\n"
        f"1. Extract if at least a MONTH is mentioned. If the exact day is missing, use the 1st (e.g., 20261001).\n"
        f"2. Format the 'description' field EXACTLY like this:\n"
        f"Link: {source_url}\n"
        f"Format: [Typ des Events]\n"
        f"Inhalt bzw. Relevanz: [Max 2 Sätze Relevanz]\n"
        f"3. Output MUST be a JSON list: [{{summary, start(YYYYMMDD), end(YYYYMMDD), location, type, description}}].\n"
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
    if any(e.get("link") == link for e in db["events"].values()):
        return False

    print(f"  * Scrape: {link}")
    try:
        headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'}
        response = requests.get(link, headers=headers, timeout=15)
        soup = BeautifulSoup(response.text, 'html.parser')
        for s in soup(["script", "style", "nav", "footer", "header"]): s.decompose()
        content = soup.get_text()[:6000]
        
        time.sleep(2)
        found_events = extract_details_with_ai(content, link)
        
        new_added = False
        for event in found_events:
            start = event.get("start", "")
            end = event.get("end", "")
            if not start or (start.endswith("0101") and end.endswith("1231")):
                continue
                
            if is_duplicate(event, db):
                print(f"    ⏩ Dublette übersprungen: {event['summary']}")
                continue
            
            event["link"] = link
            event["status"] = "active"
            uid = hashlib.md5((event["summary"] + start).encode()).hexdigest()
            db["events"][uid] = event
            print(f"    ✅ NEU: {event['summary']} ({start})")
            new_added = True
        return new_added
    except Exception as e:
        print(f"    ❌ Fehler bei {link}: {e}")
        return False

def generate_ics(db):
    ics = [
        "BEGIN:VCALENDAR", 
        "VERSION:2.0", 
        "PRODID:-//DesignBot//DE", 
        "X-WR-CALNAME:Design Events 2026", 
        "X-WR-TIMEZONE:Europe/Berlin",
        "METHOD:PUBLISH"
    ]
    for eid, e in db["events"].items():
        desc = e.get('description', '').replace('\n', '\\n')
        ics.extend([
            "BEGIN:VEVENT",
            f"UID:{eid}",
            f"SUMMARY:{e['summary']}",
            f"DTSTART;VALUE=DATE:{e['start']}",
            f"DTEND;VALUE=DATE:{e.get('end', e['start'])}",
            f"LOCATION:{e.get('location', 'TBA/Online')}",
            f"DESCRIPTION:{desc}",
            "END:VEVENT"
        ])
    ics.append("END:VCALENDAR")
    with open(ICS_FILE, "w", encoding="utf-8") as f:
        f.write("\n".join(ics))

def main():
    db = load_db()
    
    # 1. Seeds
    print(">>> Verarbeite Seed-Liste...")
    for url in SEED_URLS:
        process_url(url, db)
        save_db(db)

    # 2. Suche in DE und EN (beide werden pro Run geprüft)
    print("\n>>> Starte Suche...")
    for lang, conf in SPRACH_MAPPING.items():
        for thema in THEMEN:
            # Wir nehmen das erste Format der Liste für die Suche
            query = f"{thema} {conf['formate'][0]} {conf['ort']} 2026"
            print(f"--- Query ({lang}): {query} ---")
            try:
                r = requests.post("https://google.serper.dev/search", 
                                  headers={'X-API-KEY': os.getenv("SERPER_API_KEY")}, 
                                  json={"q": query, "num": 8}).json()
                for item in r.get('organic', []):
                    process_url(item['link'], db)
                    save_db(db)
            except: continue

    generate_ics(db)
    print("\n>>> Kalender aktualisiert.")

if __name__ == "__main__":
    main()
