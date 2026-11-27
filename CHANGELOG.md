# Changelog

## v2.1.0 – 2026-11-27

Sicherheits- und Komfort-Update: Anmeldeseite statt Browser-Passwortfenster, besser lesbare Oberfläche, Tests vor jedem Release. Enthält auch die Korrekturen aus dem Review (geplant als v2.0.1).

**Docker-Nutzer:** neue `docker-compose.yml` übernehmen (Volume `hermesvi_data` für die Anmeldungen), dann `docker compose pull && docker compose up -d` und auf jedem Gerät einmal anmelden. Mit `ALLOW_NO_AUTH=true` ist jetzt `ALLOWED_HOSTS` Pflicht.

**Anmeldung (Docker)**
- Neu: eigene Anmeldeseite. Das Passwort geht nur beim Anmelden über die Leitung; danach ein zufälliges Token im Cookie (`HttpOnly`, `Secure`, `SameSite=Strict`). Auf dem Server liegt nur dessen Hash. Geräte bleiben 30 Tage angemeldet (`SESSION_DAYS`) – auch die iPhone-Web-App fragt nicht mehr zwischendurch
- Neu: „Abmelden“ und „Alle Geräte abmelden“ im System-Bereich; ein neues Passwort meldet alle Geräte ab
- Neu: Passwort nur als scrypt-Hash speichern – `APP_PASSWORD_HASH`, erzeugen mit `docker compose run --rm hermesvi python server.py hash-password`
- Passwort-Sperre zusätzlich global (100 Fehlversuche insgesamt); die Liste der Fehlversuche wird bei vielen Adressen gekürzt statt komplett gelöscht. Angemeldete Geräte bleiben von der Sperre unberührt
- Basic-Auth funktioniert weiterhin für Skripte, zeigt aber kein Browser-Passwortfenster mehr

**Sicherheit**
- Kanban-Meldungen: Standard ist jetzt `NOTIFY_MODE=announce` (nur Titel und Status ansagen). Im Modus `agent` baut der Server die Nachricht an den Agenten selbst – der Browser sieht das Ergebnis nicht mehr und kann es nicht verändern; jede Meldung geht höchstens einmal an den Agenten. **Steht in deiner `hermesvi.env` noch `NOTIFY_MODE=agent`, bleibt es bei diesem Verhalten**
- `ALLOW_NO_AUTH=true` ohne `ALLOWED_HOSTS` startet nicht mehr (Schutz gegen DNS-Rebinding)
- Fehlermeldungen im Browser ohne interne Adressen und ohne Antworttexte von Hermes/ElevenLabs – Details im Log
- `ELEVENLABS_VOICE_ID` wird geprüft (nur Buchstaben/Ziffern)
- Zusätzliche Header: `Cross-Origin-Opener-Policy`, `Cross-Origin-Resource-Policy`; Caddy- und nginx-Vorlagen setzen HSTS
- Desktop: Ändert sich die Hermes-, Dashboard- oder Audio-Adresse, wird der zugehörige Key gelöscht und muss neu eingegeben werden. Der Hermes-Key geht nur noch an ein Audio-Plugin auf demselben Rechner
- Desktop: Electron-Fuses gesperrt (kein `ELECTRON_RUN_AS_NODE`, kein `NODE_OPTIONS`, kein `--inspect`), App-Code nur aus `app.asar`

**Oberfläche**
- Behoben: Bei Fensterbreiten unter 1300 px überlappte „Tippen, um das Gespräch zu starten“ den Status
- Behoben: Im breiten Desktop-Layout war der Mikrofon-Pegel unten abgeschnitten
- Reiter im Panel mit Abstand, nichts wird mehr abgeschnitten
- Besser lesbar: Beschriftungen mindestens 12 px, weniger Sperrschrift, hellerer Nebentext
- Sichtbarer Fokus-Rahmen für die Tastaturbedienung, Beschriftungen für Screenreader; „Bewegung reduzieren“ beruhigt den Orb
- Demo-Modus zeigt Beispiel-Aufträge und Log statt leerer Spalten
- iPhone: richtiges App-Symbol auf dem Home-Bildschirm (einmal entfernen und neu hinzufügen)
- Kanban-Meldungen an den Agenten sind im Chat als „automatisch“ gekennzeichnet
- Lagebild wird im Hintergrund (Handy) nicht mehr abgefragt

**Technik**
- Eine Oberfläche für beide Varianten: `ui/` ist die einzige Quelle, `scripts/sync-ui.mjs` verteilt sie
- Tests: `pytest tests/` (Anmeldung, Schutz, Kanban, Anhänge, Layout im Browser bei drei Fenstergrößen) und `node --test tests/desktop.test.js`. Laufen bei jedem Pull Request; ohne grüne Tests kein Release
- FastAPI `lifespan` statt veraltetem `on_event`; Hintergrund-Task für das Lagebild wird sicher gehalten
- Edge-Stimme mit Zeitlimit; Länge der Nachricht wird vor dem Auslesen der Anhänge geprüft
- Standard-Stimmmodell überall `eleven_flash_v2_5`
- Docker-Image zusätzlich als `:2` (Hauptversion); die Compose-Vorlage nutzt `:2` statt `:latest`

## v2.0.0 – 2026-11-27

Großes Update: neues Layout für alle Fenstergrößen, stabile Windows-App. Fasst v1.3.2 bis v1.3.5 zusammen.

- **Windows-App läuft wieder vollständig:** Seit v1.3.1 blockierte die Sicherheitsrichtlinie (CSP) das Skript der Oberfläche – kein Kreis, keine Uhr, kein Status, kein Einstellungen-Knopf. Behoben
- **Schmale Fenster und Handy:** Kreis, Status, Untertitel, Eingabefeld und Knöpfe stehen sauber untereinander und überlappen nicht mehr; der Kreis ist kleiner und passt sich dem Platz an
- **Neu: Lautsprecher-Knopf** neben dem Mikrofon – Vorlesen überall mit einem Klick an/aus, synchron mit „Vorlesen“ und den Einstellungen
- **Breites Desktop-Layout:** rechte Spalte aufgeräumt – Aktivität oben (2/3), System und Einstellungen unten (max. 1/3, scrollt); keine übereinanderliegenden Bereiche mehr
- Aktivität zeigt Werkzeug-Ergebnisse lesbar statt „[object Object]“
- Repo erzwingt LF-Zeilenenden (`.gitattributes`)

## v1.3.5 – 2026-11-27

- Behoben: Im breiten Desktop-Layout lagen rechts Aufträge und Aktivität übereinander, wenn vorher im schmalen Fenster der Reiter „Aufträge“ oder „Log“ gewählt war
- Rechte Spalte neu aufgeteilt: Aktivität oben (2/3), System und Einstellungen unten (max. 1/3, scrollt)
- Behoben: Aktivität zeigte bei manchen Werkzeug-Ergebnissen „[object Object]“ – jetzt der Inhalt (gekürzt)

## v1.3.4 – 2026-11-27

- Neu: Lautsprecher-Knopf neben dem Mikrofon – Vorlesen auch im schmalen Fenster und auf dem Handy an- und ausschalten (vorher nur im breiten Desktop-Layout oder über die Einstellungen). Bleibt mit dem „Vorlesen“-Knopf und der Einstellung synchron
- Handy: Knöpfe etwas kleiner, damit alle in eine Reihe passen

## v1.3.3 – 2026-11-27

Wichtiger Fix für die Windows-App.

- Behoben: In der Windows-App (seit v1.3.1) lief das Skript der Oberfläche nicht – kein Kreis, keine Uhr, kein Status, kein Einstellungen-Knopf. Ursache: Der Windows-Build hatte Windows-Zeilenenden, dadurch passte der Sicherheits-Hash (Content-Security-Policy) nicht und der Browser blockierte das Skript. Hash wird jetzt unabhängig von Zeilenenden berechnet, das Repo erzwingt LF (`.gitattributes`)
- Linux-App und Docker waren nicht betroffen

## v1.3.2 – 2026-11-27

Layout-Fix für schmalere Fenster und Handy.

- Behoben: Bei Fenstern unter 1300 px Breite schob sich das Eingabefeld „Schreib etwas …“ über längere Untertitel. Kreis, Status, Untertitel, Eingabefeld und Buttons stehen jetzt untereinander und können sich nicht mehr überlappen
- Der Kreis ist kleiner und nutzt nur noch den freien Platz – auf flachen Bildschirmen schrumpft er mit
- Untertitel mit Mindesthöhe, damit der Kreis beim Erscheinen von Text nicht springt; bei niedrigen Fenstern etwas kleinere Schrift
- Buttons sauber mittig ausgerichtet

## v1.3.1 – 2026-11-23

Sicherheits-Update nach einem zweiten Sicherheits-Check. **Docker-Nutzer: neue `docker-compose.yml` übernehmen und `LISTEN_IP` setzen (siehe unten).**

- **Wichtig – nur noch im VPN lauschen:** Caddy bindet jetzt an `LISTEN_IP` (NetBird-IP des Docker-Hosts) statt an alle Netze. Vorher öffnete Docker 80/443 auf allen Adressen – auch auf öffentlichen IPv6-Adressen und an der Host-Firewall vorbei. Einrichten: `echo "LISTEN_IP=100.64.0.20" > .env` neben der Compose-Datei
- Behoben: Die Hostnamen-Sperre (`ALLOWED_HOSTS`) ließ sich mit einem gefälschten `X-Forwarded-Host` umgehen. `X-Forwarded-Host/-For` gelten jetzt nur noch von vertrauenswürdigen Proxys (`TRUSTED_PROXIES`, Standard: lokal + Docker-Netze); die nginx-Vorlage setzt den Header selbst
- Behoben: Die Passwort-Sperre ließ sich ohne Proxy mit wechselndem `X-Forwarded-For` umgehen
- Behoben: Das Größenlimit (12 MB) ließ sich mit `Transfer-Encoding: chunked` umgehen – greift jetzt immer, und erst nach der Anmeldung
- Anhänge: PDF und Word werden in einem eigenen Prozess gelesen – ohne Zugangsdaten, mit Zeit- (30 s), Rechen- (20 s) und Speicherlimit (768 MB), ohne Schreibrechte. Präparierte Dateien können den Server nicht mehr blockieren (vorher bis zu 2 s Stillstand bei einem 300-Seiten-PDF)
- Neu: Anhänge abschaltbar – `ATTACH_ENABLED=false` (Docker) bzw. Schalter in den Desktop-Einstellungen
- Content-Security-Policy ohne `unsafe-inline` für Skripte: nur die eigenen Skripte laufen (per Hash)
- Sitzungsnamen und Dateinamen werden bereinigt, bevor sie an Hermes bzw. in den Prompt gehen; Chat-Verlauf pro Sitzung begrenzt
- Brücken-Token wird geprüft, bevor der Inhalt gelesen wird
- Herkunftsnachweis (GitHub-Attestierung) für alle Downloads und das Docker-Image: `gh attestation verify <Datei> --repo ITCLucke/HermesVI`
- Dependabot hält Actions, Basis-Image, Python- und npm-Pakete aktuell
- Start-Warnung bei `ALLOW_NO_AUTH=true` ohne Passwort; Doku empfiehlt `APP_PASSWORD` auch hinter dem Proxy

## v1.3.0 – 2026-11-23

Fotos und Dateien an den Agenten schicken.

- Neu: Anhängen per Büroklammer (Handy: neben dem Mikrofon, Desktop: links im Chat), per Einfügen (Strg+V) oder Hineinziehen
- Neu: Fotos und Screenshots gehen als Bild an Hermes – der Agent sieht sie direkt. Große Handy-Fotos werden vorher im Browser verkleinert (max. 1600 px), iPhone-Fotos (HEIC) dabei zu JPEG
- Neu: Aus Word (.docx), Text-, Markdown-, CSV-, JSON- und Code-Dateien wird der Text ausgelesen und klar als Daten gekennzeichnet mitgeschickt
- Neu (Docker): PDFs – der Text wird ausgelesen. Eingescannte PDFs ohne Text bitte als Foto schicken
- Anhänge warten unten, bis du etwas sagst oder schreibst – auch per Sprache: Foto anhängen, „Was ist das?“ sagen
- Max. 5 Anhänge pro Nachricht, je 8 MB; Vorschau mit Entfernen-Knopf; Anhänge erscheinen im Chat und im Verlauf
- Docker: neue Einstellung `ATTACH_MAX_CHARS` (Standard 40000 Zeichen Text pro Dokument), neue Abhängigkeit pypdf 7.1.1
- Desktop-App: Bilder, Word und Text ja, PDF noch nicht

## v1.2.3 – 2026-11-23

Die Docker-Variante gibt es jetzt fertig zum Herunterladen.

- Neu: Fertiges Docker-Image `ghcr.io/itclucke/hermesvi` (amd64 und arm64) bei jedem Release, Tags `1.2.3`, `1.2` und `latest`
- Neu: Release-Download `HermesVI-Docker-v1.2.3.zip` mit Compose-Datei, Vorlagen (`hermesvi.env.example`, Caddy, nginx) und Quellcode
- Updates jetzt einfach: `docker compose pull && docker compose up -d` – keine Dateien mehr kopieren, kein eigener Build nötig
- Selbst bauen bleibt möglich (z. B. für lokale Spracherkennung): in `docker-compose.yml` `build: .` einkommentieren
- **Umstieg von 1.2.2 oder älter:** neue `docker-compose.yml` aus dem Paket übernehmen (`hermesvi.env` und `Caddyfile.docker` bleiben), dann `docker compose pull && docker compose up -d`
- Enthält den iPhone-Fix aus 1.2.2 (Mikrofon nach App-Wechsel)

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
