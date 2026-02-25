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

def save_db(db):
    with open(DATABASE_FILE, "w", encoding="utf-8") as f:
        json.dump(db, f, indent=2, ensure_ascii=False)

def generate_id(text):
    return hashlib.md5(text.encode()).hexdigest()

def get_page_content(url):
    try:
        headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'}
        response = requests.get(url, headers=headers, timeout=15)
        soup = BeautifulSoup(response.text, 'html.parser')
        for s in soup(["script", "style", "nav", "footer"]): s.extract()
        return soup.get_text()[:6000]
    except Exception as e:
        print(f"  ! Fehler beim Laden der Seite: {e}")
        return ""

def extract_details_with_ai(page_text, source_url):
    if not GEMINI_KEY: return None
    
    # Wir probieren verschiedene Modell-Varianten, um den 404 zu umgehen
    model_names = ['gemini-1.5-flash', 'gemini-1.5-flash-latest']
    
    prompt = f"""
    Extrahiere Event-Details für 2026. Quelle: {source_url}
    Antworte NUR als JSON:
    {{
      "summary": "Name",
      "start": "YYYYMMDD",
      "end": "YYYYMMDD",
      "location": "Stadt oder Online-Event",
      "type": "Konferenz/Meetup/Workshop/Festival",
      "priority": 1-5,
      "description": "Ein Satz Info"
    }}
    Wenn kein Event 2026 gefunden wird: null.
    Text: {page_text}
    """

    for m_name in model_names:
        try:
            genai.configure(api_key=GEMINI_KEY)
            model = genai.GenerativeModel(m_name)
            time.sleep(1) # Rate-Limit Schutz
            response = model.generate_content(prompt)
            content = response.text.replace("```json", "").replace("```", "").strip()
            return json.loads(content)
        except Exception as e:
            print(f"  ! KI-Versuch mit {m_name} fehlgeschlagen: {e}")
            continue
    return None

def main():
    # Datenbank laden
    if os.path.exists(DATABASE_FILE):
        with open(DATABASE_FILE, "r", encoding="utf-8") as f:
            db = json.load(f)
    else:
        db = {"events": {}}

    keywords = [
        "Service Design Konferenz 2026 Europa", 
        "UX Design Events 2026 Deutschland",
        "Public Sector Innovation Events 2026"
    ]
    
    for kw in keywords:
        print(f"\n>>> Suche: {kw}")
        if not SERPER_KEY: break
        
        try:
            res = requests.post("https://google.serper.dev/search", 
                                headers={'X-API-KEY': SERPER_KEY, 'Content-Type': 'application/json'},
                                data=json.dumps({"q": kw}))
            results = res.json().get('organic', [])
        except:
            continue

        for res in results:
            link = res.get('link')
            link_id = generate_id(link)

            if link_id in db["events"]:
                print(f"  . Bekannt: {link[:50]}...")
                continue

            print(f"  * Analysiere: {link}")
            text = get_page_content(link)
            if not text or len(text) < 200: continue
            
            details = extract_details_with_ai(text, link)
            
            if details and details.get("start"):
                details["link"] = link
                details["status"] = "active"
                db["events"][link_id] = details
                print(f"    => GEFUNDEN: {details['summary']}")
                # Sofort speichern, damit nichts verloren geht
                save_db(db)
            else:
                db["events"][link_id] = {"status": "ignored", "link": link}
                save_db(db)

    # Am Ende ICS aus allen aktiven Events bauen
    generate_ics(db["events"])

def generate_ics(events_dict):
    ics_lines = ["BEGIN:VCALENDAR", "VERSION:2.0", "PRODID:-//EventBot//DE", "METHOD:PUBLISH"]
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
