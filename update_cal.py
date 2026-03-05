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
THEMEN = [
    "Service Design Government", 
    "Service Design",
    "UX Design",
    "User Experience Design",
    "UX/UI Design",
    "UX Public Sector", 
    "GovTech Innovation", 
    "Digital Accessibility Conference",
    "E-Government User Experience",
    "Civic Design",
    "Smart City Service Design"
]

SPRACH_MAPPING = {
    "de": {"ort": "Deutschland", "formate": ["Konferenz", "Workshop", "Meet-up", "Vortrag"]},
    "en": {"ort": "Europe", "formate": ["Conference", "Workshop", "Summit", "Talk"]}
}

SEED_URLS = [
    "https://www.service-design-network.org/events",
    "https://uxpa.org/calendar/",
    "https://uxconf.de/",
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
            
            # --- MIGRATION: Alte Einträge auf das neue Format umstellen ---
            updated_events = {}
            for k, v in db.get("events", {}).items():
                # Sicherstellen, dass neue Felder existieren
                if "source_link" not in v:
                    v["source_link"] = v.get("link", "N/A")
                if "event_format" not in v:
                    v["event_format"] = v.get("type", "Event")
                if "relevance" not in v:
                    v["relevance"] = v.get("description", "No description provided.")
                updated_events[k] = v
            db["events"] = updated_events
            return db
    return {"events": {}}

def save_db(db):
    with open(DATABASE_FILE, "w", encoding="utf-8") as f:
        json.dump(db, f, indent=2, ensure_ascii=False)

def extract_details_with_ai(text, source_url):
    prompt = (
        f"Analyze for Design/UX events in 2026. SOURCE URL: {source_url}\n"
        f"STRICT GEOGRAPHIC RULE: ONLY extract events in EUROPE or ONLINE. No USA/Canada.\n"
        f"STRICT DATA RULES:\n"
        f"1. 'start' and 'end' MUST be YYYYMMDD.\n"
        f"2. Each object MUST have these fields:\n"
        f"   - 'summary': Name\n"
        f"   - 'start': YYYYMMDD\n"
        f"   - 'end': YYYYMMDD\n"
        f"   - 'location': City or Online\n"
        f"   - 'event_format': e.g. Conference, Workshop\n"
        f"   - 'relevance': 1-2 sentences about content\n"
        f"   - 'source_link': '{source_url}'\n"
        f"3. If exact day is missing, use 1st day and set 'is_confirmed': false.\n"
        f"Output JSON list: [{{summary, start, end, location, event_format, relevance, source_link, is_confirmed}}]"
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
            start = str(event.get("start", ""))
            # Validierung & Status
            if re.match(r"^\d{8}$", start) and event.get("is_confirmed") is True:
                event["status"] = "active"
            else:
                event["status"] = "on_hold"
            
            # Eindeutige ID generieren
            uid = hashlib.md5((event.get("summary", "") + start).encode()).hexdigest()
            db["events"][uid] = event
            print(f"    [{event['status']}] {event.get('summary')}")
        return True
    except:
        return False

def generate_ics(db):
    ics = [
        "BEGIN:VCALENDAR", "VERSION:2.0", "PRODID:-//DesignBot//DE", 
        "X-WR-CALNAME:Design Events 2026", "METHOD:PUBLISH"
    ]
    
    count = 0
    for eid, e in db["events"].items():
        if e.get("status") == "active":
            # Das neue Wunsch-Layout:
            link = e.get("source_link", "N/A")
            fmt = e.get("event_format", "Event")
            desc = e.get("relevance", "No details.")
            
            full_description = f"Link: {link}\\nFormat: {fmt}\\nDescription: {desc}"
            
            ics.extend([
                "BEGIN:VEVENT",
                f"UID:{eid}",
                f"SUMMARY:{e['summary']}",
                f"DTSTART;VALUE=DATE:{e['start']}",
                f"DTEND;VALUE=DATE:{e.get('end', e['start'])}",
                f"LOCATION:{e.get('location', 'TBA')}",
                f"DESCRIPTION:{full_description}",
                "END:VEVENT"
            ])
            count += 1
            
    ics.append("END:VCALENDAR")
    with open(ICS_FILE, "w", encoding="utf-8") as f:
        f.write("\n".join(ics))
    print(f"\n>>> ICS bereit mit {count} Events.")

def main():
    db = load_db()
    for url in SEED_URLS: process_url(url, db)
    save_db(db)

    lang = random.choice(list(SPRACH_MAPPING.keys()))
    conf = SPRACH_MAPPING[lang]
    for thema in THEMEN:
        query = f"{thema} {conf['formate'][0]} {conf['ort']} 2026 -USA -America"
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
