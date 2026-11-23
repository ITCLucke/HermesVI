# Changelog

## v1.2.0 – 2026-11-23

Erste öffentliche Version unter dem Namen **HermesVI**.

- Neuer Projektname HermesVI (Hermes Voice Interface), App-Name, Dateien und Pakete umbenannt
- Anzeigename des Agenten frei wählbar, Standard „Hermes“ (`AGENT_NAME` in der Docker-Variante)
- Neu: `HERMES_SESSION_KEY` für den Gedächtnis-Scope in Hermes (Standard = Gesprächsfaden)
- Docker: `hermesvi.env`, Dienst und Container `hermesvi`, systemd-Unit `hermesvi.service`
- Desktop: übernimmt Einstellungen aus Vorabversionen beim ersten Start automatisch
- Orb-Stil heißt jetzt „Classic“
- MIT-Lizenz

### Bisheriger Funktionsumfang (Vorabversionen 1.0–1.1)

- Freihändiges Sprachgespräch mit dem Hermes-Hauptagenten über den Hermes API-Server (Responses-API)
- ElevenLabs: Stimme (Flash v2.5) und Spracherkennung (Scribe v2)
- Desktop-Dashboard: Aufträge und Log links, Orb und Chat in der Mitte, Aktivität und System rechts
- Kanban-Meldungen: Der Agent fasst erledigte, fehlgeschlagene und blockierte Aufträge von selbst zusammen
- Windows-App und Linux-App (AppImage/.deb) ohne Docker, Keys verschlüsselt gespeichert
- Sicherheit: CSRF-Schutz, lokaler Server nur mit Token, Kanban-Ergebnisse als fremde Daten markiert
- Sprachausgabe-Knopf gilt für alle Antworten; Ausschalten lässt die laufende Antwort sofort verstummen
