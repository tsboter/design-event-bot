import os
from google import genai

GEMINI_KEY = os.getenv("GEMINI_API_KEY")

def diagnose_and_run():
    if not GEMINI_KEY:
        print("❌ Kein API_KEY in den Secrets gefunden!")
        return

    # Initialisierung des neuen SDKs
    client = genai.Client(api_key=GEMINI_KEY)
    
    print("--- 🔍 DIAGNOSE: Verfügbare Modelle ---")
    available_models = []
    try:
        # Wir listen alle Modelle auf, die dein Key sehen darf
        for m in client.models.list():
            print(f"ID: {m.name} | Support: {m.supported_methods}")
            available_models.append(m.name)
    except Exception as e:
        print(f"❌ Fehler beim Abrufen der Modell-Liste: {e}")
        return

    if not available_models:
        print("❌ Dein Key sieht aktuell ÜBERHAUPT KEINE Modelle. (Key-Aktivierung abwarten?)")
        return

    # Wir suchen uns das passende Modell aus der Liste
    # Manche Keys brauchen das Präfix "models/", manche nicht.
    target = None
    for candidate in ["gemini-1.5-flash", "gemini-1.5-flash-latest", "gemini-2.0-flash-exp"]:
        # Wir prüfen sowohl mit als auch ohne "models/" Präfix
        for m in available_models:
            if candidate in m:
                target = m
                break
        if target: break

    if not target:
        target = available_models[0] # Notfall: Nimm das erste verfügbare
    
    print(f"\n--- 🚀 TESTLAUF mit Modell: {target} ---")
    try:
        response = client.models.generate_content(
            model=target,
            contents="Hallo! Antworte kurz mit 'System bereit'."
        )
        print(f"✅ Erfolg: {response.text}")
    except Exception as e:
        print(f"❌ Test fehlgeschlagen mit {target}: {e}")

if __name__ == "__main__":
    diagnose_and_run()
