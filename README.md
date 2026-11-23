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

- **Docker-Variante: Zugangsschutz ist Pflicht.** Entweder `APP_PASSWORD` setzen oder – wenn der Reverse-Proxy schon schützt (z. B. *Access List* im Nginx Proxy Manager) – `ALLOW_NO_AUTH=true`. Ohne eines von beiden verweigert HermesVI den Dienst.
- **Kanban-Meldungen:** Im Modus `agent` gibt HermesVI das Ergebnis eines Auftrags an den Agenten weiter. Es kann fremde Inhalte enthalten (Mails, Webseiten) und ist trotz Kennzeichnung ein Einfallstor für Prompt-Injection. Vorsichtiger: `NOTIFY_MODE=announce` bzw. in der Desktop-App „Nur ansagen“.
- **Mikrofon:** Freihändig heißt auch, dass Fernseher, Videos oder Gäste mitreden können. Mikro aus, wenn du nicht da bist.
- **Hermes:** für gefährliche Befehle eine Bestätigung verlangen, soweit dein Hermes-Setup das anbietet.
- **Firewall auf dem Hermes-Rechner:** Ports 8642 und 9119 nur für den Docker-Host und deine PCs freigeben.
- **Dashboard-Token** ist ein Generalschlüssel fürs Hermes-Dashboard. Nie teilen, bei Verdacht neu erzeugen.
- **Fernzugriff** nur über VPN (z. B. NetBird, WireGuard, Tailscale), nie offen ins Internet.
- **ElevenLabs:** Key nur mit den zwei nötigen Rechten und mit Credit-Limit.
- **Anhänge:** Text aus Dokumenten wird als fremde Daten gekennzeichnet – trotzdem können präparierte Dateien (z. B. PDFs aus Mails) versuchen, den Agenten zu steuern. Nur Dateien schicken, denen du vertraust.
- `chmod 600 hermesvi.env`

Eingebaute Schutzmaßnahmen:
- Keys bleiben auf dem Server bzw. verschlüsselt im Benutzerkonto (Linux: Warnung, wenn kein Schlüsselbund da ist; Einstellungsdatei nur für den eigenen Benutzer lesbar)
- Schutz gegen fremde Webseiten (CSRF), Content-Security-Policy, kein Einbetten in fremde Seiten (Clickjacking)
- Passwort-Sperre nach 10 Fehlversuchen, optional nur bestimmte Hostnamen (`ALLOWED_HOSTS`, gegen DNS-Rebinding)
- Größenlimits (Text 64 KB, Sprache 10 MB, Anfrage 12 MB)
- Desktop-Server nur auf `127.0.0.1` mit Token pro Start, Fenster kann keine fremden Seiten laden
- Kanban-Ergebnisse werden als fremde Daten markiert; jede Meldung bearbeitet nur ein Gerät
- Docker-Container: schreibgeschützt, ohne Root, ohne Linux-Capabilities
- Releases mit `SHA256SUMS.txt` zum Prüfen der Downloads

## Installation

- **Docker:** siehe [`docker/README.md`](docker/README.md). Kurz: `HermesVI-Docker-vX.zip` aus den [Releases](../../releases) entpacken, `hermesvi.env` aus `hermesvi.env.example` anlegen, `docker compose up -d`. Das fertige Image liegt unter `ghcr.io/itclucke/hermesvi` (amd64 + arm64); Updates mit `docker compose pull && docker compose up -d`.
- **Windows:** `HermesVI-Windows-vX.zip` aus den [Releases](../../releases) entpacken und `HermesVI.exe` starten. Selbst bauen: `cd desktop && npm ci && npm run pack:win`
- **Linux:** `HermesVI-Linux-vX-amd64.deb` per Doppelklick installieren (oder `sudo apt install ./HermesVI-Linux-….deb`), danach im Menü „HermesVI“. Alternativ die `.AppImage` ausführbar machen (`chmod +x`) und starten. Selbst bauen: `cd desktop && npm ci && npm run pack:linux`

Beim ersten Start der Desktop-App öffnen sich die Einstellungen: Hermes-URL und Key, optional ElevenLabs-Key und Dashboard-Token eintragen.

## Neue Version veröffentlichen

1. Änderungen machen, `CHANGELOG.md` um einen Abschnitt `## vX.Y.Z – Datum` ergänzen.
2. Neue Versionsnummer in `VERSION` eintragen und nach `main` pushen.
3. GitHub Actions (`.github/workflows/release.yml`) baut Windows- und Linux-App, das Docker-Image (`ghcr.io/itclucke/hermesvi:X.Y.Z`, `:X.Y`, `:latest`) und das Docker-Paket, legt den Tag `vX.Y.Z` an und veröffentlicht das Release.

Pushes ohne neue Versionsnummer lösen kein Release aus. Einmalig nötig:
Repo → Settings → Actions → General → Workflow permissions → „Read and write permissions“.

## Hinweis

HermesVI ist ein unabhängiges Community-Projekt und nicht mit Nous Research verbunden. „Hermes Agent“ bezeichnet hier nur die Software, mit der HermesVI zusammenarbeitet.

## Lizenz

[MIT](LICENSE)
