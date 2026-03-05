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
THEMEN = [
    "Service Design Government", 
    "UX Public Sector Europe", 
    "GovTech Conference 2026", 
    "Digital Accessibility Public Sector",
    "Civic Design Innovation Europe"
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

# Deine festen Quellen
SEED_URLS = [
    "https://www.service-design-network.org/events",
    "https://uxpa.org/calendar/",
    "https://uxconf.de/"
]

DATABASE_FILE = "data.json"
ICS_FILE = "events.ics"
TARGET_MODEL = "models/gemini-1.5-flash"

# API Keys aus den GitHub Secrets
SERPER_KEY = os.getenv("SERPER_API_KEY")
GEMINI_KEY = os.getenv("GEMINI_API_KEY")

client = genai.Client(api_key=GEMINI_KEY)

def load_db():
    if os.path.exists(DATABASE_FILE):
        with open(DATABASE_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    return {"events": {}}

def extract_details_with_ai(text):
    prompt = (
        "Extract professional Design/UX/GovTech events for 2026 or 2027 in Europe from the text. "
        "Return a JSON list: [{\"summary\": \"...\", \"start\": \"YYYYMMDD\", \"end\": \"YYYYMMDD\", "
        "\"location\": \"...\", \"type\": \"...\", \"relevance\": \"...\", \"is_confirmed\": true}]. "
        "Important: If you find an event but the exact day is missing, use YYYYMM01. "
        "Text: " + text
    )
    try:
        response = client.models.generate_content(model=TARGET_MODEL, contents=prompt, config={'response_mime_type': 'application/json'})
        # DEBUG: Zeig uns was die KI denkt
        print(f"    [KI-Rohdaten]: {response.text[:200]}...") 
        data = json.loads(response.text)
        return data if isinstance(data, list) else [data]
    except Exception as e:
        print(f"    [KI-Fehler]: {e}")
        return []

def process_url(link, db):
    print(f"  * Scrape: {link}")
    try:
        response = requests.get(link, headers={'User-Agent': 'Mozilla/5.0'}, timeout=15)
        soup = BeautifulSoup(response.text, 'html.parser')
        content = soup.get_text()[:6000]
        
        found_events = extract_details_with_ai(content)
        
        if not found_events:
            print("    ∅ Keine Events auf dieser Seite gefunden.")
            
        for event in found_events:
            start = str(event.get("start", ""))
            event["source_link"] = link
            
            # LOCKERERE REGEL: Wenn ein Datum da ist, nehmen wir es erst mal auf!
            if re.match(r"^\d{8}$", start):
                event["status"] = "active"
            else:
                event["status"] = "on_hold"

            uid = hashlib.md5((event.get("summary", "") + start).encode()).hexdigest()
            db["events"][uid] = event
            print(f"    ✅ GEFUNDEN: {event.get('summary')} ({start})")
        return True
    except:
        return False

def run_serper_search(query):
    """Sucht bei Google nach neuen Event-Links."""
    print(f"🔍 Suche nach: {query}")
    try:
        url = "https://google.serper.dev/search"
        payload = json.dumps({"q": query, "num": 5})
        headers = {'X-API-KEY': SERPER_KEY, 'Content-Type': 'application/json'}
        response = requests.request("POST", url, headers=headers, data=payload)
        return [item['link'] for item in response.json().get('organic', [])]
    except Exception as e:
        print(f"⚠️ Serper Fehler: {e}")
        return []

def generate_ics(db):
    ics = ["BEGIN:VCALENDAR", "VERSION:2.0", "PRODID:-//DesignBot//DE", "X-WR-CALNAME:Design Events 2026", "METHOD:PUBLISH"]
    count = 0
    for e in db["events"].values():
        if e.get("status") == "active":
            link = e.get("source_link", "N/A")
            fmt = e.get("type", "Event")
            desc = e.get("relevance", "N/A")
            
            full_desc = f"Link: {link}\\nFormat: {fmt}\\nDescription: {desc}"
            
            ics.extend([
                "BEGIN:VEVENT",
                f"SUMMARY:{e['summary']}",
                f"DTSTART;VALUE=DATE:{e['start']}",
                f"DTEND;VALUE=DATE:{e.get('end', e['start'])}",
                f"LOCATION:{e.get('location', 'TBA')}",
                f"DESCRIPTION:{full_desc}",
                "END:VEVENT"
            ])
            count += 1
    ics.append("END:VCALENDAR")
    with open(ICS_FILE, "w", encoding="utf-8") as f:
        f.write("\n".join(ics))
    print(f"\n>>> ICS bereit mit {count} bestätigten Events.")

def main():
    db = load_db()
    
    # 1. Bekannte Quellen prüfen
    print(">>> Prüfe Seeds...")
    for url in SEED_URLS:
        process_url(url, db)
    
    # 2. Über Serper neue Quellen finden (Rotation: 2 Themen pro Run)
    selected_themes = random.sample(THEMEN, 2)
    print(f"\n>>> Starte Recherche für: {selected_themes}")
    for thema in selected_themes:
        new_links = run_serper_search(thema)
        for link in new_links:
            process_url(link, db)
            # Kleiner Sleep um APIs zu schonen
            time.sleep(1)

    # 3. Speichern
    with open(DATABASE_FILE, "w", encoding="utf-8") as f:
        json.dump(db, f, indent=2, ensure_ascii=False)
    
    generate_ics(db)

if __name__ == "__main__":
    main()
