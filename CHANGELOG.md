# Changelog

## v1.2.2 – 2026-11-23

Fehlerbehebung für die Web-App auf dem Handy (vor allem iPhone/iPad als Homescreen-App).

- Behoben: Nach einem App-Wechsel oder dem Wegwischen blieb das Mikrofon belegt (orangener Punkt), und bei der Rückkehr reagierte der Agent nicht mehr – nur Schließen und neu Öffnen half
- Neu: Geht die App auf dem Handy in den Hintergrund, gibt sie Mikrofon und Audio sauber frei. Bei der Rückkehr erscheint „Tippen, um weiterzumachen“ – ein Tippen genügt (iOS erlaubt Audio nur nach einer Berührung)
- Neu: Fällt das Mikrofon unterwegs aus (Anruf, Siri, Headset-Wechsel), erkennt die App das und bietet ebenfalls den Neustart per Tippen an
- Unverändert: Desktop-App und Desktop-Browser hören im Hintergrund weiter zu
- Hinweis: iOS merkt sich die Mikrofon-Freigabe für Homescreen-Apps teilweise nicht dauerhaft und fragt nach einem Neustart der App eventuell erneut – das lässt sich von der App aus nicht ändern

## v1.2.1 – 2026-11-23

Sicherheits-Update nach einer vollständigen Code-Prüfung.

**Bitte beachten (Docker):** Zugangsschutz ist jetzt Pflicht. In `hermesvi.env` `APP_PASSWORD` setzen oder `ALLOW_NO_AUTH=true`, wenn dein Reverse-Proxy schon schützt – sonst nimmt HermesVI keine Befehle an.

- Behoben: Mit `APP_PASSWORD` waren Aufträge und Hermes-Log über `GET /api/state` trotzdem ohne Passwort abrufbar
- Behoben: Kanban-Meldungen wurden bei mehreren offenen Geräten mehrfach an den Agenten geschickt – jetzt bearbeitet sie genau ein Gerät
- Behoben: Einstellungsfenster (Desktop) konnte Antworten eines manipulierten Servers als HTML ausführen
- Neu: Meldungsmodus „Nur ansagen“ (`NOTIFY_MODE=announce`) – Ergebnisse aus Aufträgen erreichen den Agenten dann nicht automatisch
- Neu: Content-Security-Policy und Schutz gegen Einbetten in fremde Seiten (beide Varianten)
- Neu: Sperre nach 10 falschen Passwörtern für 15 Minuten
- Neu: Größenlimits für Text, Sprache und Anfragen; ungültige Werte führen nicht mehr zu Serverfehlern
- Neu: `ALLOWED_HOSTS` gegen DNS-Rebinding (optional)
- Desktop: Einstellungsdatei nur für den eigenen Benutzer lesbar, Warnung bei fehlendem Linux-Schlüsselbund, Adressen und Werte werden geprüft
- Docker: Container ohne Linux-Capabilities, mit Prozess- und Speicherlimit
- Chat-Modus: Verlauf im Speicher begrenzt
- Release: `SHA256SUMS.txt` zum Prüfen der Downloads, GitHub Actions auf aktuelle Versionen gehoben
- python-multipart 0.0.34

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
