import os
import json
import hashlib
import requests
import time
from bs4 import BeautifulSoup
import google.generativeai as genai

# --- KONFIGURATION ---
SERPER_KEY = os.getenv("SERPER_API_KEY")
GEMINI_KEY = os.getenv("GEMINI_API_KEY")
DATABASE_FILE = "data.json"
ICS_FILE = "events.ics"

# Gemini KI Setup
if GEMINI_KEY:
    genai.configure(api_key=GEMINI_KEY)
    model = genai.GenerativeModel('gemini-1.5-flash')

def generate_id(text):
    """Erzeugt eine eindeutige ID (MD5 Hash)."""
    return hashlib.md5(text.encode()).hexdigest()

def get_page_content(url):
    """Liest den Textinhalt einer Webseite."""
    try:
        headers = {'User-Agent': 'Mozilla/5.0'}
        response = requests.get(url, headers=headers, timeout=10)
        soup = BeautifulSoup(response.text, 'html.parser')
        for s in soup(["script", "style"]): s.extract()
        return soup.get_text()[:5000]
    except:
        return ""

def extract_details_with_ai(page_text, source_url):
    """KI-Extraktion mit Fehlerbehandlung."""
    if not GEMINI_KEY: return None
    
    prompt = f"""
    Extrahiere Event-Details für 2026 aus diesem Text.
    Quelle: {source_url}
    Antworte NUR als JSON:
    {{
      "summary": "Name",
      "start": "YYYYMMDD",
      "end": "YYYYMMDD",
      "location": "Stadt oder Online-Event",
      "type": "Konferenz/Meetup/Workshop/Festival",
      "priority": 1-5,
      "description": "Ein Satz"
    }}
    Wenn kein Event 2026 gefunden wird, antworte mit: null
    Text: {page_text}
    """
    try:
        # Kurze Pause für das Rate-Limit (Free Tier)
        time.sleep(2) 
        response = model.generate_content(prompt)
        content = response.text.replace("```json", "").replace("```", "").strip()
        return json.loads(content)
    except Exception as e:
        print(f"KI-Fehler: {e}")
        return None

def main():
    # 1. Datenbank laden (Wichtig: Wir laden sie EINMAL am Anfang)
    if os.path.exists(DATABASE_FILE):
        with open(DATABASE_FILE, "r", encoding="utf-8") as f:
            db = json.load(f)
    else:
        db = {"events": {}}

    keywords = ["Service Design Events 2026", "UX Design Konferenz 2026", "Public Sector Innovation 2026"]
    
    for kw in keywords:
        print(f"--- Suche nach: {kw} ---")
        if not SERPER_KEY: break
        
        search_url = "https://google.serper.dev/search"
        res = requests.post(search_url, 
                            headers={'X-API-KEY': SERPER_KEY, 'Content-Type': 'application/json'},
                            data=json.dumps({"q": kw}))
        results = res.json().get('organic', [])

        for res in results:
            link = res.get('link')
            # WICHTIG: Wir nutzen den LINK als ID für den Vor-Check
            link_id = generate_id(link)

            if link_id in db["events"]:
                print(f"Überspringe (bereits bekannt): {link}")
                continue

            print(f"Analysiere: {link}")
            text = get_page_content(link)
            if not text: continue
            
            details = extract_details_with_ai(text, link)
            
            if details and details.get("start"):
                # Event mit dem Link als Key speichern
                details["link"] = link
                details["status"] = "active"
                db["events"][link_id] = details
                print(f"GEFUNDEN: {details['summary']}")
            else:
                # Damit wir nicht jedes Mal denselben unbrauchbaren Link scannen:
                db["events"][link_id] = {"status": "ignored", "link": link}

    # 2. Datenbank speichern (WICHTIG: Überschreibt die data.json mit dem neuen Stand)
    with open(DATABASE_FILE, "w", encoding="utf-8") as f:
        json.dump(db, f, indent=2, ensure_ascii=False)

    # 3. ICS generieren
    generate_ics(db["events"])

def generate_ics(events_dict):
    ics_lines = ["BEGIN:VCALENDAR", "VERSION:2.0", "PRODID:-//Bot//DE", "METHOD:PUBLISH"]
    for e_id, e in events_dict.items():
        if e.get("status") == "active":
            stars = "⭐" * int(e.get('priority', 1))
            summary = f"[{e.get('type', 'EVENT').upper()}] {stars} {e['summary']}"
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

if __name__ == "__main__":
    main()
