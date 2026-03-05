import os
import json
import hashlib
import requests
import time
import random
import re
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

client = genai.Client(api_key=os.getenv("GEMINI_API_KEY"))

def load_db():
    if os.path.exists(DATABASE_FILE):
        with open(DATABASE_FILE, "r", encoding="utf-8") as f:
            db = json.load(f)
            # BEREINIGUNG: Wir fixen alte "TBA" Einträge direkt beim Laden
            clean_events = {}
            for k, v in db.get("events", {}).items():
                start = str(v.get("start", ""))
                # Wenn das Datum keine 8 Zahlen sind, setzen wir es auf on_hold
                if not re.match(r"^\d{8}$", start):
                    v["status"] = "on_hold"
                clean_events[k] = v
            db["events"] = clean_events
            return db
    return {"events": {}}

def save_db(db):
    with open(DATABASE_FILE, "w", encoding="utf-8") as f:
        json.dump(db, f, indent=2, ensure_ascii=False)

def extract_details_with_ai(text, source_url):
    prompt = (
        f"Analyze for Design/UX events in 2026. "
        f"STRICT DATE RULES:\n"
        f"1. 'start' and 'end' MUST be YYYYMMDD (e.g. 20261015). NEVER use 'TBA' or strings.\n"
        f"2. If the EXACT DAY is known: set 'is_confirmed': true.\n"
        f"3. If ONLY the MONTH is known: use YYYYMM01 and set 'is_confirmed': false.\n"
        f"4. Description format: Link: {source_url}\\nFormat: [Typ]\\nInhalt: [Relevanz].\n"
        f"Output JSON list: [{{summary, start, end, is_confirmed, location, description}}]"
    )
    try:
        response = client.models.generate_content(model=TARGET_MODEL, contents=prompt, config={'response_mime_type': 'application/json'})
        data = json.loads(response.text)
        return data if isinstance(data, list) else [data]
    except:
        return []

def process_url(link, db):
    print(f"  * Analysiere: {link}")
    try:
        headers = {'User-Agent': 'Mozilla/5.0'}
        response = requests.get(link, headers=headers, timeout=15)
        soup = BeautifulSoup(response.text, 'html.parser')
        for s in soup(["script", "style", "nav", "footer", "header"]): s.decompose()
        content = soup.get_text()[:6000]
        
        found_events = extract_details_with_ai(content, link)
        
        for event in found_events:
            start = str(event.get("start", ""))
            
            # --- DIE NEUE SICHERHEITSSCHLEUSE ---
            # Prüfe ob Startdatum exakt 8 Ziffern sind
            is_valid_date = re.match(r"^\d{8}$", start)
            
            if is_valid_date and event.get("is_confirmed") is True:
                event["status"] = "active"
            else:
                event["status"] = "on_hold"
            
            # Verhindere Ganzjahres-Events (01.01. bis 31.12.)
            if start.endswith("0101") and str(event.get("end", "")).endswith("1231"):
                event["status"] = "on_hold"

            uid = hashlib.md5((event.get("summary", "") + start).encode()).hexdigest()
            db["events"][uid] = event
            
            status_emoji = "✅" if event["status"] == "active" else "⏳"
            print(f"    {status_emoji} {event.get('summary')} [{event['status']}]")
        return True
    except Exception as e:
        print(f"    ❌ Fehler: {e}")
        return False

def generate_ics(db):
    ics = ["BEGIN:VCALENDAR", "VERSION:2.0", "PRODID:-//DesignBot//DE", "X-WR-CALNAME:Design Events 2026", "METHOD:PUBLISH"]
    active_count = 0
    for eid, e in db["events"].items():
        # Nur Einträge mit Status 'active' UND gültigem 8-stelligem Datum
        if e.get("status") == "active" and re.match(r"^\d{8}$", str(e.get("start", ""))):
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
    print(f"\n>>> ICS generiert: {active_count} bestätigte Events.")

def main():
    db = load_db()
    for url in SEED_URLS: process_url(url, db)
    save_db(db)

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
