# HermesVI – Voice Interface für Hermes Agent

**HermesVI** (Hermes Voice Interface) ist eine Sprach- und Dashboard-Oberfläche für den [Hermes Agent](https://github.com/NousResearch/hermes-agent). Du redest einfach mit deinem Hauptagenten, ohne Absenden, wie in einem Gespräch. Er antwortet mit seinem Gedächtnis, seinen Skills und Werkzeugen und spricht mit seiner eigenen Stimme. Daneben siehst du live seine Aufträge (Kanban), das Hermes-Log und welche Werkzeuge er gerade benutzt.

Zwei Varianten, gleiche Oberfläche:

| | `docker/` | `desktop/` |
|---|---|---|
| Für | Handy und Browser (auch PC) | Windows-PC und Linux (Ubuntu/Mint) |
| Läuft | als Container auf einem Docker-Host | als `HermesVI.exe` bzw. `.deb`/`.AppImage`, ohne Docker |
| Erreichbar | über deinen Reverse-Proxy per HTTPS (z. B. `https://hermesvi.lan.example`) | lokal, kein HTTPS/DNS nötig |
| Keys | `hermesvi.env` auf dem Docker-Host | verschlüsselt im Benutzerkonto (Windows DPAPI / Linux-Schlüsselbund) |
| Gesprächsfaden | `hermesvi` | `hermesvi-pc` |

Beide können denselben Hermes-API-Key (`API_SERVER_KEY`) parallel nutzen.

## Funktionen

- Freihändiges Gespräch: reden ohne Absenden, Unterbrechen durch Reinreden
- Stimme per ElevenLabs (Flash v2.5), Spracherkennung per ElevenLabs Scribe; alternativ lokales Whisper, Edge-TTS oder Browser-Stimme
- Desktop ab 1300 px: links Aufträge (2/3) und Hermes-Log (1/3), Mitte animierter Orb und Chat, rechts Aktivität und System
- Handy: Orb im Vollbild, Panel mit Verlauf, Aktivität, Aufträgen, Log und System; als Web-App auf den Home-Bildschirm legbar
- Chat: tippen oder sprechen, Sprachausgabe an/aus
- Anhänge: Fotos, Screenshots und Dokumente mitschicken – per Büroklammer, Einfügen (Strg+V) oder Hineinziehen. Bilder sieht der Agent direkt, aus Word (.docx), Text- und Code-Dateien liest HermesVI den Text aus; PDF nur in der Docker-Variante
- Kanban-Meldungen: Der Agent meldet sich von selbst, wenn ein Auftrag erledigt, fehlgeschlagen oder blockiert ist
- Aufträge, Log und Meldungen kommen direkt aus dem Hermes-Dashboard (`HERMES_DASHBOARD_SESSION_TOKEN`)
- Anzeigename des Agenten frei wählbar (`AGENT_NAME` bzw. in den Einstellungen)
- Docker: eigene Anmeldeseite – einmal anmelden, das Gerät bleibt 30 Tage angemeldet; „Abmelden“ und „Alle Geräte abmelden“ im System-Bereich

Nur Desktop: Symbol im Infobereich, Tastenkürzel Strg+Umschalt+Leertaste, Autostart, Benachrichtigungen, Einstellungsfenster.
Ubuntu/GNOME (Wayland) erlaubt Apps keine globalen Tastenkürzel. Dort in den Systemeinstellungen ein eigenes Kürzel auf `hermesvi --toggle-mic` legen. Unter Linux Mint/Cinnamon funktioniert es direkt.

## Hermes vorbereiten (einmalig)

In `~/.hermes/.env` des Agenten-Profils (bzw. `~/.hermes/profiles/<profil>/.env`):

```sh
API_SERVER_ENABLED=true
API_SERVER_HOST=0.0.0.0              # nur nötig, wenn HermesVI auf einem anderen Rechner läuft
API_SERVER_KEY=<openssl rand -hex 24>
API_SERVER_MODEL_NAME=<name-deines-agenten>
HERMES_DASHBOARD_SESSION_TOKEN=<python3 -c "import secrets;print(secrets.token_urlsafe(32))">
```

Danach `hermes gateway restart` und `systemctl --user restart hermes-dashboard`.

- API-Server: `http://<hermes-host>:8642` · Dashboard: `http://<hermes-host>:9119`
- ElevenLabs-Key braucht die Rechte „Text to Speech“ und „Speech to Text“.
- Das Plugin `hermes-audio-api` wird **nicht** gebraucht. Bei einem Gateway mit mehreren Profilen startet es ohnehin nicht.

## Sicherheit

Ein Hermes-Agent hat in der Regel vollen Terminal-Zugriff auf seinen Rechner. **Wer dem Agenten Befehle geben kann, kann alles, was der Agent kann.** Deshalb:

- **Docker-Variante: Zugangsschutz ist Pflicht.** `APP_PASSWORD` (oder besser `APP_PASSWORD_HASH`, siehe [`docker/README.md`](docker/README.md)) setzen – empfohlen auch hinter einem schützenden Reverse-Proxy. `ALLOW_NO_AUTH=true` nur, wenn der Proxy zuverlässig schützt (z. B. *Access List* im Nginx Proxy Manager), und dann zusammen mit `ALLOWED_HOSTS`. Ohne Zugangsschutz verweigert HermesVI den Dienst.
- **Nur im VPN lauschen:** In der Compose-Datei bindet Caddy an `LISTEN_IP` (NetBird-IP des Docker-Hosts). Sonst öffnet Docker die Ports auf allen Netzen – auch auf öffentlichen IPv6-Adressen und an der Host-Firewall vorbei.
- **Kanban-Meldungen:** Standard ist `NOTIFY_MODE=announce` – HermesVI sagt nur Titel und Status an, das Ergebnis erreicht den Agenten erst, wenn du fragst. Im Modus `agent` gibt HermesVI das Ergebnis selbst an den Agenten weiter. Es kann fremde Inhalte enthalten (Mails, Webseiten) und ist trotz Kennzeichnung ein Einfallstor für Prompt-Injection.
- **Mikrofon:** Freihändig heißt auch, dass Fernseher, Videos oder Gäste mitreden können. Mikro aus, wenn du nicht da bist.
- **Hermes:** für gefährliche Befehle eine Bestätigung verlangen, soweit dein Hermes-Setup das anbietet.
- **Firewall auf dem Hermes-Rechner:** Ports 8642 und 9119 nur für den Docker-Host und deine PCs freigeben.
- **Dashboard-Token** ist ein Generalschlüssel fürs Hermes-Dashboard. Nie teilen, bei Verdacht neu erzeugen.
- **Fernzugriff** nur über VPN (z. B. NetBird, WireGuard, Tailscale), nie offen ins Internet.
- **ElevenLabs:** Key nur mit den zwei nötigen Rechten und mit Credit-Limit.
- **Anhänge:** Text aus Dokumenten wird als fremde Daten gekennzeichnet – trotzdem können präparierte Dateien (z. B. PDFs aus Mails) oder Text in Bildern versuchen, den Agenten zu steuern. Nur Dateien schicken, denen du vertraust, und in Hermes eine Bestätigung für gefährliche Befehle verlangen. Abschalten: `ATTACH_ENABLED=false` bzw. Schalter in den Desktop-Einstellungen.
- **Verbindung Docker-Host → Hermes-VM** läuft per HTTP mit dem API-Key im Klartext. Beide am besten über die interne Proxmox-Bridge bzw. ein eigenes VLAN verbinden, nicht durchs normale Heimnetz – oder TLS davor.
- `chmod 600 hermesvi.env`

Eingebaute Schutzmaßnahmen:
- Anmeldeseite statt Browser-Passwortfenster: Das Passwort geht nur beim Anmelden über die Leitung, danach ein zufälliges Token im Cookie (`HttpOnly`, `Secure`, `SameSite=Strict`). Auf dem Server liegt nur dessen Hash; Abmelden sperrt es sofort, ein neues Passwort meldet alle Geräte ab
- Passwort optional nur als scrypt-Hash in der Konfiguration (`APP_PASSWORD_HASH`)
- Keys bleiben auf dem Server bzw. verschlüsselt im Benutzerkonto (Linux: Warnung, wenn kein Schlüsselbund da ist; Einstellungsdatei nur für den eigenen Benutzer lesbar). Desktop: Ändert sich eine Adresse, wird der zugehörige Key gelöscht und muss neu eingegeben werden
- Schutz gegen fremde Webseiten (CSRF), Content-Security-Policy ohne `unsafe-inline` für Skripte (nur die eigenen, per Hash), kein Einbetten in fremde Seiten (Clickjacking)
- Passwort-Sperre nach 10 Fehlversuchen pro Adresse und nach 100 insgesamt (bestehende Anmeldungen bleiben), optional nur bestimmte Hostnamen (`ALLOWED_HOSTS`, gegen DNS-Rebinding; Pflicht bei `ALLOW_NO_AUTH`); `X-Forwarded-*` gilt nur von vertrauenswürdigen Proxys (`TRUSTED_PROXIES`)
- Fehlermeldungen im Browser ohne interne Adressen oder Antworttexte fremder Dienste – Details stehen im Log
- Größenlimits (Text 64 KB, Sprache 10 MB, Anfrage 12 MB – auch bei Chunked-Übertragung)
- PDF/Word-Anhänge werden in einem eigenen Prozess ohne Zugangsdaten und mit Zeit-/Speicherlimit gelesen
- Herkunftsnachweis für alle Downloads und das Docker-Image: `gh attestation verify <Datei> --repo ITCLucke/HermesVI`
- Desktop-Server nur auf `127.0.0.1` mit Token pro Start, Fenster kann keine fremden Seiten laden; Electron-Fuses gesperrt (kein `ELECTRON_RUN_AS_NODE`, kein `NODE_OPTIONS`, kein `--inspect`, App-Code nur aus `app.asar`)
- Kanban-Ergebnisse werden als fremde Daten markiert; jede Meldung bearbeitet nur ein Gerät
- Docker-Container: schreibgeschützt, ohne Root, ohne Linux-Capabilities
- Releases mit `SHA256SUMS.txt` zum Prüfen der Downloads; ein Release entsteht nur, wenn alle Tests grün sind

## Installation

- **Docker:** siehe [`docker/README.md`](docker/README.md). Kurz: `HermesVI-Docker-vX.zip` aus den [Releases](../../releases) entpacken, `hermesvi.env` aus `hermesvi.env.example` anlegen, `docker compose up -d`. Das fertige Image liegt unter `ghcr.io/itclucke/hermesvi` (amd64 + arm64); Updates mit `docker compose pull && docker compose up -d`.
- **Windows:** `HermesVI-Windows-vX.zip` aus den [Releases](../../releases) entpacken und `HermesVI.exe` starten. Selbst bauen: `cd desktop && npm ci && npm run pack:win`
- **Linux:** `HermesVI-Linux-vX-amd64.deb` per Doppelklick installieren (oder `sudo apt install ./HermesVI-Linux-….deb`), danach im Menü „HermesVI“. Alternativ die `.AppImage` ausführbar machen (`chmod +x`) und starten. Selbst bauen: `cd desktop && npm ci && npm run pack:linux`

Beim ersten Start der Desktop-App öffnen sich die Einstellungen: Hermes-URL und Key, optional ElevenLabs-Key und Dashboard-Token eintragen.

## Aufbau des Repos

| Ordner | Inhalt |
|---|---|
| `ui/` | Die Oberfläche – **einzige Quelle** für beide Varianten (`index.html`, `login.html` für Docker, `settings.html` für Desktop, Icons) |
| `docker/` | Web-Server (`server.py`), Compose-Datei, Proxy-Vorlagen. `docker/static/` wird aus `ui/` erzeugt |
| `desktop/` | Electron-App (`main.js`, `server.js`, `settings.js`). `desktop/ui/` wird aus `ui/` erzeugt |
| `scripts/sync-ui.mjs` | kopiert `ui/` nach `docker/static/` und `desktop/ui/` – vor jedem lokalen Build: `node scripts/sync-ui.mjs` (die Desktop-Skripte `npm start` / `npm run pack:*` machen das selbst) |
| `tests/` | `pytest tests/` (Docker-Server + Oberfläche im Browser), `node --test tests/desktop.test.js` (Desktop) |

## Neue Version veröffentlichen

1. Änderungen machen, `CHANGELOG.md` um einen Abschnitt `## vX.Y.Z – Datum` ergänzen.
2. Neue Versionsnummer in `VERSION` eintragen und nach `main` pushen.
3. GitHub Actions (`.github/workflows/release.yml`) lässt zuerst alle Tests laufen (`test.yml`), baut dann Windows- und Linux-App, das Docker-Image (`ghcr.io/itclucke/hermesvi:X.Y.Z`, `:X.Y`, `:X`, `:latest`) und das Docker-Paket, legt den Tag `vX.Y.Z` an und veröffentlicht das Release. Pull Requests werden automatisch getestet.

Pushes ohne neue Versionsnummer lösen kein Release aus. Einmalig nötig:
Repo → Settings → Actions → General → Workflow permissions → „Read and write permissions“.

## Hinweis

HermesVI ist ein unabhängiges Community-Projekt und nicht mit Nous Research verbunden. „Hermes Agent“ bezeichnet hier nur die Software, mit der HermesVI zusammenarbeitet.

## Lizenz

[MIT](LICENSE)
