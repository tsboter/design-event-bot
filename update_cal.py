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

# Client-Initialisierung
client = genai.Client(api_key=GEMINI_KEY) if GEMINI_KEY else None

def save_db(db):
    with open(DATABASE_FILE, "w", encoding="utf-8") as f:
        json.dump(db, f, indent=2, ensure_ascii=False)

def get_page_content(url):
    try:
        headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'}
        response = requests.get(url, headers=headers, timeout=12)
        soup = BeautifulSoup(response.text, 'html.parser')
        for s in soup(["script", "style", "nav", "footer"]): s.extract()
        return soup.get_text()[:7000]
    except:
        return ""

def extract_details_with_ai(page_text, source_url):
    if not client: return None
    
    # Wir versuchen das modernste Modell
    target_model = "gemini-2.0-flash"
    
    prompt = f"Extrahiere Event-Details für 2026 als JSON (summary, start, end, location, type, priority, description). Quelle: {source_url}. Text: {page_text}"

    try:
        response = client.models.generate_content(
            model=target_model,
            contents=prompt,
            config={
                'response_mime_type': 'application/json',
            }
        )
        # Das neue SDK kann das JSON oft direkt parsen
        return json.loads(response.text)
    except Exception as e:
        print(f"  ! Fehler mit {target_model}: {e}")
        # Kleiner Diagnose-Check: Was ist eigentlich verfügbar?
        try:
            print("  ? Verfügbare Modelle für deinen Key:")
            for m in client.models.list():
                print(f"    - {m.name}")
        except: pass
        return None

def main():
    if os.path.exists(DATABASE_FILE):
        with open(DATABASE_FILE, "r", encoding="utf-8") as f:
            db = json.load(f)
    else:
        db = {"events": {}}

    # Deine Suchbegriffe
    queries = ["Service Design Konferenz 2026", "UX Design Events 2026", "Public Sector Innovation 2026"]
    
    for query in queries:
        print(f"\n>>> Suche: {query}")
        search_res = requests.post("https://google.serper.dev/search", 
                                   headers={'X-API-KEY': SERPER_KEY},
                                   json={"q": query})
        
        for res in search_res.json().get('organic', []):
            link = res.get('link')
            link_id = hashlib.md5(link.encode()).hexdigest()

            if link_id in db["events"]:
                continue

            print(f"  * Analysiere: {link}")
            content = get_page_content(link)
            if not content: continue
            
            time.sleep(2) # Höflichkeitspause
            details = extract_details_with_ai(content, link)
            
            if details and details.get("start"):
                details["link"] = link
                details["status"] = "active"
                db["events"][link_id] = details
                print(f"    => GEFUNDEN: {details['summary']}")
                save_db(db)
            else:
                db["events"][link_id] = {"status": "ignored", "link": link}
                save_db(db)

    generate_ics(db["events"])

def generate_ics(events_dict):
    # (Logik bleibt gleich wie im vorherigen Schritt)
    ics_lines = ["BEGIN:VCALENDAR", "VERSION:2.0", "PRODID:-//EventBot//DE", "METHOD:PUBLISH"]
    for e_id, e in events_dict.items():
        if e.get("status") == "active":
            summary = f"[{e.get('type', 'EVENT').upper()}] {e['summary']}"
            ics_lines.extend(["BEGIN:VEVENT", f"UID:{e_id}", f"SUMMARY:{summary}",
                              f"DTSTART;VALUE=DATE:{e['start']}", f"DTEND;VALUE=DATE:{e['end']}",
                              f"LOCATION:{e['location']}", f"DESCRIPTION:{e.get('link','')}", "END:VEVENT"])
    ics_lines.append("END:VCALENDAR")
    with open(ICS_FILE, "w", encoding="utf-8") as f:
        f.write("\n".join(ics_lines))

if __name__ == "__main__":
    main()
