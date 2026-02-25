import json
import hashlib
import os

DATABASE_FILE = "data.json"
ICS_FILE = "events.ics"

def generate_id(summary, date):
    # Erstellt eine eindeutige ID basierend auf Name und Startdatum
    return hashlib.md5(f"{summary}{date}".encode()).hexdigest()

def load_data():
    if os.path.exists(DATABASE_FILE):
        with open(DATABASE_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    return {"events": {}}

def save_data(data):
    with open(DATABASE_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)

def update_event_data(existing, new_data):
    # Logik für Updates: Nur überschreiben, wenn neue Info "gehaltvoller" ist
    updated = False
    for key in ["location", "description"]:
        new_val = new_data.get(key, "")
        # Update wenn das alte Feld leer war oder Platzhalter enthielt (TBA / tbd)
        if len(new_val) > len(existing.get(key, "")) or "tba" in existing.get(key, "").lower():
            if new_val:
                existing[key] = new_val
                updated = True
    return updated

def main():
    db = load_data()
    
    # SIMULATION: Hier würde dein Scraper-Ergebnis stehen
    # Ich nehme hier beispielhaft ein Event mit wenig Info
    scraped_events = [
        {
            "summary": "Creative Bureaucracy Festival 2026",
            "start": "20260611",
            "end": "20260612",
            "location": "Radialsystem, Berlin",
            "description": "Details folgen bald."
        }
    ]

    for event in scraped_events:
        e_id = generate_id(event["summary"], event["start"])
        
        # 1. Dopplung & Gelöschte vermeiden
        if e_id in db["events"]:
            if db["events"][e_id].get("status") == "deleted":
                continue # Ignorieren, da manuell gelöscht
            
            # 2. Bestehende Events updaten (falls mehr Infos da sind)
            update_event_data(db["events"][e_id], event)
        else:
            # 3. Neu aufnehmen
            event["status"] = "active"
            db["events"][e_id] = event

    save_data(db)
    generate_ics(db["events"])

def generate_ics(events_dict):
    ics_content = "BEGIN:VCALENDAR\nVERSION:2.0\nPRODID:-//EventBot//DE\nMETHOD:PUBLISH\n"
    for e_id, e in events_dict.items():
        if e.get("status") == "active":
            ics_content += "BEGIN:VEVENT\n"
            ics_content += f"UID:{e_id}\n"
            ics_content += f"SUMMARY:{e['summary']}\n"
            ics_content += f"DTSTART;VALUE=DATE:{e['start']}\n"
            ics_content += f"DTEND;VALUE=DATE:{e['end']}\n"
            ics_content += f"LOCATION:{e['location']}\n"
            ics_content += f"DESCRIPTION:{e['description']}\n"
            ics_content += "END:VEVENT\n"
    ics_content += "END:VCALENDAR"
    
    with open(ICS_FILE, "w", encoding="utf-8") as f:
        f.write(ics_content)

if __name__ == "__main__":
    main()
