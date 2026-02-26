import os
import json
import hashlib
import requests
import time
from bs4 import BeautifulSoup
from google import genai

# --- ANPASSBARE KONFIGURATION ---
# Hier kannst du Themen und Orte einfach erweitern oder ändern:
THEMEN = ["Service Design", "UX Design", "Public Sector Innovation", "Design Thinking"]
FORMATE = ["Konferenz", "Workshop", "Meet-up", "Talk", "Event"]
ORTE = ["Berlin", "Deutschland", "Europa", "Online"]

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
    # Bereinigung: Wir behalten nur aktive Events, um die Datei sauber zu halten
    with open(DATABASE_FILE, "w", encoding="utf-8") as f:
        json.dump(db, f, indent=2, ensure_ascii=False)

def generate_search_queries():
    """Erstellt Suchbegriffe basierend auf Themen, Formaten und Orten."""
    queries = []
    for thema in THEMEN:
        for ort in ORTE:
            # Beispiel: "Service Design Konferenz Berlin 2026"
            queries.append(f"{thema} {' '.join(FORMATE[:2])} {ort} 2026")
    return queries[:15] # Limit auf 15 Anfragen pro Run

def is_duplicate(new_event, db):
    """Prüft auf inhaltliche Dubletten (gleicher Titel am gleichen Tag)."""
    new_summary = new_event.get("summary", "").lower().strip()
    new_start = new_event.get("start", "")
    
    for eid, e in db["events"].items():
        if e.get("status") == "active":
            old_summary = e.get("summary", "").lower().strip()
            old_start = e.get("start", "")
            # Wenn Titel fast gleich UND Datum gleich -> Dublette
            if new_summary == old_summary and new_start == old_start:
                return True
    return False

def extract_details_with_ai(text, source_url):
    """KI-Prompt mit Fokus auf deine Formate und Hierarchie."""
    formate_str = ", ".join(FORMATE)
    orte_str = ", ".join(ORTE)
    
    prompt = (
        f"Extrahiere ausschließlich folgende Formate: {formate_str}. "
        f"Priorisiere Orte in dieser Hierarchie: {orte_str}. "
        f"Erstelle ein JSON-Array mit Events für 2026. "
        f"Felder: summary, start (YYYYMMDD), end (YYYYMMDD), location, type, description. "
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
    """Erzeugt eine saubere, einzelne ICS Datei."""
    ics = [
        "BEGIN:VCALENDAR",
        "VERSION:2.0",
        "PRODID:-//DesignEventBot//DE",
        "X-WR-CALNAME:Design Events 2026",
        "X-WR-TIMEZONE:Europe/Berlin",
        "METHOD:PUBLISH",
        "CALSCALE:GREGORIAN"
    ]
    
    for eid, e in db["events"].items():
        if e.get("status") == "active" and e.get("start"):
            ics.extend([
                "BEGIN:VEVENT",
                f"UID:{eid}",
                f"SUMMARY:{e['summary']}",
                f"DTSTART;VALUE=DATE:{e['start']}",
                f"DTEND;VALUE=DATE:{e.get('end', e['start'])}",
                f"LOCATION:{e.get('location', 'Unbekannt')}",
                f"DESCRIPTION:Typ: {e.get('type', 'Event')}\\nLink: {e.get('link', '')}",
                "END:VEVENT"
            ])
    
    ics.append("END:VCALENDAR")
    with open(ICS_FILE, "w", encoding="utf-8") as f:
        f.write("\n".join(ics))
    print(f">>> {ICS_FILE} wurde mit allen aktuellen Events überschrieben.")

def main():
    db = load_db()
    queries = generate_search_queries()
    
    for query in queries:
        print(f"\n>>> Suche: {query}")
        try:
            res = requests.post("https://google.serper.dev/search", 
                                headers={'X-API-KEY': SERPER_KEY},
                                json={"q": query, "num": 5}).json()
        except: continue
        
        for item in res.get('organic', []):
            link = item['link']
            # Link-basiertes ID-System
            link_id = hashlib.md5(link.encode()).hexdigest()
            
            if link_id in db["events"]: continue
            
            print(f"  * Check: {link}")
            try:
                page = requests.get(link, timeout=10).text
                content = BeautifulSoup(page, 'html.parser').get_text()[:4000]
            except: continue
            
            time.sleep(2)
            found_events = extract_details_with_ai(content, link)
            
            for event in found_events:
                if not event or not isinstance(event, dict) or not event.get("start"):
                    continue
                
                # Dubletten-Check (inhaltlich)
                if is_duplicate(event, db):
                    print(f"    ⏩ Dublette ignoriert: {event['summary']}")
                    continue

                event["link"] = link
                event["status"] = "active"
                db["events"][link_id] = event
                print(f"    ✅ NEU: {event['summary']} am {event['start']}")
                save_db(db)

    generate_ics(db)

if __name__ == "__main__":
    main()
