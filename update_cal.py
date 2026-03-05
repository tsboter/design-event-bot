import os
import json
import hashlib
import requests
import time
import random
import re
from datetime import datetime, timedelta
from bs4 import BeautifulSoup
from google import genai

# --- CONFIG ---
THEMEN = ["Service Design", "UX Design", "Public Sector Innovation", "Strategic Design"]
SPRACH_MAPPING = {
    "de": {"ort": "Deutschland", "formate": ["Konferenz", "Workshop", "Meet-up", "Vortrag"]},
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
CLEANUP_DAYS = 14  # Wie lange ein 'on_hold' Event ohne Update überlebt

client = genai.Client(api_key=os.getenv("GEMINI_API_KEY"))

def load_db():
    if os.path.exists(DATABASE_FILE):
        try:
            with open(DATABASE_FILE, "r", encoding="utf-8") as f:
                db = json.load(f)
                
                # --- AUTO-CLEANUP & VALIDATION ---
                now = time.time()
                clean_events = {}
                cutoff = now - (CLEANUP_DAYS * 86400)
                
                for k, v in db.get("events", {}).items():
                    start_val = str(v.get("start", ""))
                    # 1. Validiere Format (nur 8 Ziffern erlaubt)
                    is_valid = bool(re.match(r"^\d{8}$", start_val))
                    
                    if not is_valid:
                        v["status"] = "on_hold"
                    
                    # 2. Lösche alte 'on_hold' Einträge, die nie aktualisiert wurden
                    added_at = v.get("added_at", now)
                    if v["status"] == "on_hold" and added_at < cutoff:
                        continue # Wird nicht in clean_events übernommen
                        
                    clean_events[k] = v
                
                db["events"] = clean_events
                return db
        except: pass
    return {"events": {}}

def save_db(db):
    with open(DATABASE_FILE, "w", encoding="utf-8") as f:
        json.dump(db, f, indent=2, ensure_ascii=False)

def extract_details_with_ai(text, source_url):
    prompt = (
        f"Analyze for Design/UX events in 2026. "
        f"STRICT DATE RULES:\n"
        f"1. 'start' and 'end' MUST be YYYYMMDD strings (e.g. 20261015). NEVER use 'TBA'.\n"
        f"2. If the EXACT DAY is found: set 'is_confirmed': true.\n"
        f"3. If ONLY THE MONTH is known: use YYYYMM01 and set 'is_confirmed': false.\n"
        f"4. Description structure: Link: {source_url}\\nFormat: [Typ]\\nInhalt: [Relevanz].\n"
        f"Output JSON list: [{{summary, start, end, is_confirmed, location, description}}]"
    )
    try:
        response = client.models.generate_content(model=TARGET_MODEL, contents=prompt, config={'response_mime_type': 'application/json'})
        data = json.loads(response.text)
        return data if isinstance(data, list) else [data]
    except:
        return []

def process_url(link, db):
    print(f"  * Scrape: {link}")
    try:
        headers = {'User-Agent': 'Mozilla/5.0'}
        response = requests.get(link, headers=headers, timeout=15)
        soup = BeautifulSoup(response.text, 'html.parser')
        for s in soup(["script", "style", "nav", "footer", "header"]): s.decompose()
        content = soup.get_text()[:6000]
        
        found_events = extract_details_with_ai(content, link)
        
        for event in found_events:
            start_str = str(event.get("start", ""))
            
            # Validierung: 8 Ziffern?
            if re.match(r"^\d{8}$", start_str) and event.get("is_confirmed") is True:
                # Ausschluss von Ganzjahres-Platzhaltern (01.01. - 31.12.)
                if start_str.endswith("0101") and str(event.get("end", "")).endswith("1231"):
                    event["status"] = "on_hold"
                else:
                    event["status"] = "active"
            else:
                event["status"] = "on_hold"

            uid = hashlib.md5((event.get("summary", "") + start_str).encode()).hexdigest()
            
            # Metadaten hinzufügen
            if uid not in db["events"]:
                event["added_at"] = time.time()
                
            db["events"][uid] = event
            print(f"    [{event['status'].upper()}] {event.get('summary')}")
        return True
    except:
        return False

def generate_ics(db):
    ics = ["BEGIN:VCALENDAR", "VERSION:2.0", "PRODID:-//DesignBot//DE", "X-WR-CALNAME:Design Events 2026", "METHOD:PUBLISH"]
    count = 0
    for eid, e in db["events"].items():
        # Doppelte Sicherheit beim Export
        start = str(e.get("start", ""))
        if e.get("status") == "active" and re.match(r"^\d{8}$", start):
            desc = e.get('description', '').replace('\n', '\\n')
            ics.extend([
                "BEGIN:VEVENT",
                f"UID:{eid}",
                f"SUMMARY:{e['summary']}",
                f"DTSTART;VALUE=DATE:{start}",
                f"DTEND;VALUE=DATE:{e.get('end', start)}",
                f"LOCATION:{e.get('location', 'TBA')}",
                f"DESCRIPTION:{desc}",
                "END:VEVENT"
            ])
            count += 1
    ics.append("END:VCALENDAR")
    with open(ICS_FILE, "w", encoding="utf-8") as f:
        f.write("\n".join(ics))
    print(f"\n>>> ICS generiert: {count} bestätigte Events.")

def main():
    db = load_db()
    for url in SEED_URLS: process_url(url, db)
    save_db(db)

    # Sprache rotieren
    lang = random.choice(list(SPRACH_MAPPING.keys()))
    conf = SPRACH_MAPPING[lang]
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
