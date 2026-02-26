import os
import json
import hashlib
import requests
import time
from bs4 import BeautifulSoup
from google import genai

# --- KONFIGURATION ---
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

def is_duplicate(new_summary, db):
    """Prüft, ob ein Event mit ähnlichem Titel bereits existiert."""
    new_title_clean = new_summary.lower().strip()
    for eid, e in db["events"].items():
        if e.get("status") == "active":
            if new_title_clean == e.get("summary", "").lower().strip():
                return True
    return False

def extract_details_with_ai(text, source_url):
    # Schärfere Anweisungen an die KI
    prompt = (
        f"Extrahiere NUR professionelle Events für 2026 (Konferenzen, Workshops, Talks, Summits). "
        f"Ignoriere allgemeine Werbung oder unklare Daten. "
        f"Antworte als JSON-Liste von Objekten mit: summary, start (YYYYMMDD), end (YYYYMMDD), location, type, description. "
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

def main():
    db = load_db()
    # Spezifischere Suchanfragen
    queries = [
        "Service Design Konferenz 2026", 
        "UX Design Workshops 2026", 
        "Public Innovation Talks 2026",
        "Design Thinking Events 2026 Europe"
    ]
    
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
            
            print(f"  * Analysiere: {link}")
            try:
                page = requests.get(link, timeout=10).text
                content = BeautifulSoup(page, 'html.parser').get_text()[:5000]
            except: continue
            
            time.sleep(2)
            found_events = extract_details_with_ai(content, link)
            
            for event in found_events:
                if not event.get("start") or not event.get("summary"):
                    continue
                
                # Check auf Dubletten (Titel-Vergleich)
                if is_duplicate(event["summary"], db):
                    print(f"    ⏩ Übersprungen (Dublette): {event['summary']}")
                    continue

                event["link"] = link
                event["status"] = "active"
                db["events"][link_id] = event
                print(f"    ✅ NEU: {event['summary']} ({event['start']})")
                save_db(db)

    generate_ics(db)

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
                f"LOCATION:{e.get('location','Online')}",
                f"DESCRIPTION:Typ: {e.get('type','Event')}\\nLink: {e.get('link','')}",
                "END:VEVENT"
            ])
    ics.append("END:VCALENDAR")
    with open(ICS_FILE, "w", encoding="utf-8") as f:
        f.write("\n".join(ics))

if __name__ == "__main__":
    main()
