import json
import hashlib
import os
import requests
from datetime import datetime

# Konfiguration
SERPER_API_KEY = os.getenv("SERPER_API_KEY")
DATABASE_FILE = "data.json"
ICS_FILE = "events.ics"
KEYWORDS = ["Service Design", "UX Design", "UX/UI Design", "Public Sector Design", "Öffentliches Gestalten"]
LOCATIONS = ["Europe", "Germany", "Berlin"]

def search_events(keyword, location):
    if not SERPER_API_KEY:
        print("Kein API Key gefunden!")
        return []
    
    query = f"{keyword} events {location} 2026"
    url = "https://google.serper.dev/search"
    payload = json.dumps({"q": query})
    headers = {'X-API-KEY': SERPER_API_KEY, 'Content-Type': 'application/json'}
    
    response = requests.post(url, headers=headers, data=payload)
    results = response.json().get('organic', [])
    
    found = []
    for res in results:
        # Sehr simple Extraktion aus dem Google-Snippet
        found.append({
            "summary": res.get('title'),
            "link": res.get('link'),
            "snippet": res.get('snippet'),
            "location": location
        })
    return found

def generate_id(summary):
    return hashlib.md5(summary.encode()).hexdigest()

def main():
    if os.path.exists(DATABASE_FILE):
        with open(DATABASE_FILE, "r", encoding="utf-8") as f:
            db = json.load(f)
    else:
        db = {"events": {}}

    for kw in KEYWORDS:
        for loc in LOCATIONS:
            print(f"Suche nach {kw} in {loc}...")
            new_events = search_events(kw, loc)
            
            for event in new_events:
                e_id = generate_id(event["summary"])
                
                if e_id not in db["events"]:
                    # Neues Event anlegen
                    db["events"][e_id] = {
                        "summary": event["summary"],
                        "start": "20260101", # Platzhalter, da Google Snippets oft kein ISO-Datum liefern
                        "end": "20260102",
                        "location": event["location"],
                        "description": f"Gefunden via Suche. Link: {event['link']}\nInfo: {event['snippet']}",
                        "status": "active",
                        "needs_review": True # Markierung für dich zum Prüfen
                    }
                else:
                    # Update Logik: Falls Link fehlte, jetzt aber da ist
                    if "needs_review" in db["events"][e_id]:
                        db["events"][e_id]["description"] += f"\nZusatz-Link: {event['link']}"

    with open(DATABASE_FILE, "w", encoding="utf-8") as f:
        json.dump(db, f, indent=2, ensure_ascii=False)

    generate_ics(db["events"])

def generate_ics(events_dict):
    ics_content = "BEGIN:VCALENDAR\nVERSION:2.0\nPRODID:-//DesignEventBot//DE\nMETHOD:PUBLISH\n"
    for e_id, e in events_dict.items():
        if e.get("status") == "active":
            ics_content += f"BEGIN:VEVENT\nUID:{e_id}\nSUMMARY:{e['summary']}\n"
            ics_content += f"DTSTART;VALUE=DATE:{e['start']}\nDTEND;VALUE=DATE:{e['end']}\n"
            ics_content += f"LOCATION:{e['location']}\nDESCRIPTION:{e['description']}\nEND:VEVENT\n"
    ics_content += "END:VCALENDAR"
    
    with open(ICS_FILE, "w", encoding="utf-8") as f:
        f.write(ics_content)

if __name__ == "__main__":
    main()
