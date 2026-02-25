import os
import json
import hashlib
import requests
import time
from bs4 import BeautifulSoup
from google import genai
from google.genai import errors

# --- KONFIGURATION ---
SERPER_KEY = os.getenv("SERPER_API_KEY")
GEMINI_KEY = os.getenv("GEMINI_API_KEY")
DATABASE_FILE = "data.json"
ICS_FILE = "events.ics"

client = genai.Client(api_key=GEMINI_KEY) if GEMINI_KEY else None

def save_db(db):
    with open(DATABASE_FILE, "w", encoding="utf-8") as f:
        json.dump(db, f, indent=2, ensure_ascii=False)

def get_page_content(url):
    try:
        headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'}
        response = requests.get(url, headers=headers, timeout=10)
        soup = BeautifulSoup(response.text, 'html.parser')
        for s in soup(["script", "style", "nav", "footer"]): s.extract()
        return soup.get_text()[:6000]
    except:
        return ""

def extract_details_with_ai(page_text, source_url):
    if not client: return None
    
    # Wir nehmen das "Lite" Modell, das im Free-Tier oft zuverlässiger ist
    target_model = "gemini-2.0-flash-lite"
    
    prompt = f"Extrahiere Event-Details für 2026 als JSON (summary, start, end, location, type, priority, description). Quelle: {source_url}. Text: {page_text}"

    # Retry-Logik für Quota-Fehler
    for attempt in range(3):
        try:
            response = client.models.generate_content(
                model=target_model,
                contents=prompt,
                config={'response_mime_type': 'application/json'}
            )
            return json.loads(response.text)
        except errors.ClientError as e:
            if "429" in str(e):
                print(f"  ! Quota voll. Warte 60s (Versuch {attempt+1}/3)...")
                time.sleep(60)
            else:
                print(f"  ! KI-Fehler: {e}")
                break
        except Exception as e:
            print(f"  ! Unerwarteter Fehler: {e}")
            break
    return None

def main():
    if os.path.exists(DATABASE_FILE):
        with open(DATABASE_FILE, "r", encoding="utf-8") as f:
            db = json.load(f)
    else:
        db = {"events": {}}

    queries = ["Service Design Konferenz 2026", "UX Design Events 2026", "Public Sector Innovation 2026"]
    
    for query in queries:
        print(f"\n>>> Suche: {query}")
        try:
            search_res = requests.post("https://google.serper.dev/search", 
                                       headers={'X-API-KEY': SERPER_KEY},
                                       json={"q": query, "num": 5}) # Begrenzung auf 5 Top-Links
            results = search_res.json().get('organic', [])
        except:
            continue
        
        for res in results:
            link = res.get('link')
            link_id = hashlib.md5(link.encode()).hexdigest()

            if link_id in db["events"]:
                print(f"  . Bekannt: {link[:40]}...")
                continue

            print(f"  * Analysiere: {link}")
            content = get_page_content(link)
            if len(content) < 200: continue
            
            # Warten zwischen den Anfragen, um das 15-RPM-Limit nicht zu reißen
            time.sleep(10) 
            
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
    ics_lines = ["BEGIN:VCALENDAR", "VERSION:2.0", "PRODID:-//EventBot//DE", "METHOD:PUBLISH"]
    for e_id, e in events_dict.items():
        if e.get("status") == "active":
            summary = f"[{e.get('type', 'EVENT').upper()}] {e['summary']}"
            ics_lines.extend([
                "BEGIN:VEVENT",
                f"UID:{e_id}",
                f"SUMMARY:{summary}",
                f"DTSTART;VALUE=DATE:{e['start']}",
                f"DTEND;VALUE=DATE:{e['end']}",
                f"LOCATION:{e['location']}",
                f"DESCRIPTION:{e.get('description','')} Link: {e.get('link','')}",
                "END:VEVENT"
            ])
    ics_lines.append("END:VCALENDAR")
    with open(ICS_FILE, "w", encoding="utf-8") as f:
        f.write("\n".join(ics_lines))

if __name__ == "__main__":
    main()
