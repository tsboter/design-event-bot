import os
import json
import hashlib
import requests
from bs4 import BeautifulSoup
import google.generativeai as genai

# --- KONFIGURATION ---
SERPER_KEY = os.getenv("SERPER_API_KEY")
GEMINI_KEY = os.getenv("GEMINI_API_KEY")
DATABASE_FILE = "data.json"
ICS_FILE = "events.ics"

# Sucheinstellungen
KEYWORDS = ["Service Design", "UX Design", "Public Sector Innovation", "Öffentliches Gestalten"]
LOCATIONS = ["Berlin", "Deutschland", "Europa", "Online"]

# Gemini KI Setup
if GEMINI_KEY:
    genai.configure(api_key=GEMINI_KEY)
    model = genai.GenerativeModel('gemini-1.5-flash')

def generate_id(summary, date_hint=""):
    """Erzeugt eine eindeutige ID für das Event."""
    base = f"{summary}{date_hint}"
    return hashlib.md5(base.encode()).hexdigest()

def get_page_content(url):
    """Liest den Textinhalt einer Webseite aus."""
    try:
        headers = {'User-Agent': 'Mozilla/5.0'}
        response = requests.get(url, headers=headers, timeout=15)
        soup = BeautifulSoup(response.text, 'html.parser')
        # Entferne Skripte und Styles
        for script in soup(["script", "style"]):
            script.extract()
        return soup.get_text()[:6000] # Erste 6000 Zeichen reichen meist
    except Exception as e:
        print(f"Fehler beim Laden von {url}: {e}")
        return ""

def extract_details_with_ai(page_text, source_url):
    """Nutzt Gemini, um strukturierte Daten aus dem Text zu ziehen."""
    if not GEMINI_KEY: return None
    
    prompt = f"""
    Analysiere diesen Text und extrahiere Event-Details für das Jahr 2026.
    Quelle: {source_url}

    ANFORDERUNGEN:
    - 'location': Stadt/Adresse ODER "Online-Event" (wenn remote).
    - 'type': Wähle eins: [Konferenz, Meetup, Workshop, Festival, Stammtisch].
    - 'priority': 1-5 (5=Weltweit wichtig, 1=lokales Treffen).
    - 'start' & 'end': Format YYYYMMDD (muss 2026 sein).

    Antworte NUR als valides JSON-Objekt:
    {{
      "summary": "Name des Events",
      "start": "YYYYMMDD",
      "end": "YYYYMMDD",
      "location": "Ort",
      "type": "Typ",
      "priority": 3,
      "description": "Ein Satz zum Inhalt"
    }}
    Falls kein Event für 2026 im Text ist, antworte mit: null
    Text: {page_text}
    """
    try:
        response = model.generate_content(prompt)
        content = response.text.replace("```json", "").replace("```", "").strip()
        return json.loads(content)
    except:
        return None

def search_google(query):
    """Sucht via Serper.dev nach Event-Links."""
    if not SERPER_KEY: return []
    url = "https://google.serper.dev/search"
    headers = {'X-API-KEY': SERPER_KEY, 'Content-Type': 'application/json'}
    payload = json.dumps({"q": query})
    try:
        res = requests.post(url, headers=headers, data=payload)
        return res.json().get('organic', [])
    except:
        return []

def main():
    # 1. Datenbank laden
    if os.path.exists(DATABASE_FILE):
        with open(DATABASE_FILE, "r", encoding="utf-8") as f:
            db = json.load(f)
    else:
        db = {"events": {}}

    # 2. Suche ausführen
    for kw in KEYWORDS:
        for loc in LOCATIONS:
            query = f"{kw} events {loc} 2026"
            print(f"--- Suche: {query} ---")
            results = search_google(query)
            
            for res in results:
                link = res.get('link')
                title = res.get('title')
                e_id = generate_id(title) # Vorläufige ID

                # Check: Kennen wir das Event schon oder ist es gelöscht?
                if e_id in db["events"]:
                    if db["events"][e_id].get("status") == "deleted":
                        continue
                    if not db["events"][e_id].get("needs_update", False):
                        continue # Schon bekannt und okay

                # 3. Webseite "lesen" und KI fragen
                print(f"Analysiere: {link}")
                text = get_page_content(link)
                details = extract_details_with_ai(text, link)
                
                if details and details.get("start"):
                    # Finale ID basierend auf echtem Namen/Datum
                    final_id = generate_id(details['summary'], details['start'])
                    
                    if final_id not in db["events"] or db["events"][final_id].get("status") != "deleted":
                        details["link"] = link
                        details["status"] = "active"
                        db["events"][final_id] = details
                        print(f"NEU: {details['summary']} ({details['type']})")

    # 4. Datenbank speichern
    with open(DATABASE_FILE, "w", encoding="utf-8") as f:
        json.dump(db, f, indent=2, ensure_ascii=False)

    # 5. ICS Datei generieren
    generate_ics(db["events"])

def generate_ics(events_dict):
    """Erstellt die Outlook-kompatible Kalenderdatei."""
    ics_lines = [
        "BEGIN:VCALENDAR",
        "VERSION:2.0",
        "PRODID:-//DesignEventBot//DE",
        "X-WR-CALNAME:Design & Public Sector 2026",
        "METHOD:PUBLISH"
    ]
    
    for e_id, e in events_dict.items():
        if e.get("status") == "active":
            stars = "⭐" * int(e.get('priority', 1))
            summary = f"[{e.get('type', 'Event').upper()}] {stars} {e['summary']}"
            
            ics_lines.extend([
                "BEGIN:VEVENT",
                f"UID:{e_id}",
                f"SUMMARY:{summary}",
                f"DTSTART;VALUE=DATE:{e['start']}",
                f"DTEND;VALUE=DATE:{e['end']}",
                f"LOCATION:{e['location']}",
                f"DESCRIPTION:{e['description']}\\nLink: {e.get('link','')}",
                "END:VEVENT"
            ])
            
    ics_lines.append("END:VCALENDAR")
    
    with open(ICS_FILE, "w", encoding="utf-8") as f:
        f.write("\n".join(ics_lines))
    print(f"ICS-Datei mit {len(events_dict)} Einträgen erstellt.")

if __name__ == "__main__":
    main()
