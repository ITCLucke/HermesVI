# HermesVI – Docker-/Web-Variante

Eine Web-App, in der du einfach mit deinem Hermes-Agenten redest – ohne Absenden, wie ein Gespräch.
Es antwortet dein Hermes-Hauptagent mit seinem Gedächtnis, seinen Skills und seinen Werkzeugen.
Die App zeigt ihn als lebendigen Orb an, daneben ein Panel mit Verlauf, Live-Aktivität (welche Tools er gerade nutzt) und System-Status.

```
Handy / PC (Browser)  ──NetBird──►  Caddy (HTTPS)  ──►  HermesVI :8800  ──►  Hermes API :8642   (der Agent)
                                                                              └─►  Hermes Audio :8643 (Ohren + Stimme)
```

Die Hermes-Keys bleiben auf dem Server; der Browser sieht sie nie.

> **Zugangsschutz ist Pflicht:** In `hermesvi.env` entweder `APP_PASSWORD` setzen oder `ALLOW_NO_AUTH=true`, wenn dein Reverse-Proxy schon schützt (z. B. Access List im Nginx Proxy Manager). Ohne eines von beiden zeigt HermesVI nur einen Hinweis und nimmt keine Befehle an.

## So fühlt es sich an

- App öffnen, einmal tippen (der Browser verlangt das fürs Mikro), dann einfach reden.
- Nach einer kurzen Pause (einstellbar, Standard 0,85 s) antwortet der Agent – Satz für Satz, er fängt also schon an zu sprechen, während er noch denkt.
- Reinreden unterbricht ihn. Arbeitet er gerade an einem Tool, wird das nicht abgewürgt – dein Satz wird danach verarbeitet.
- **Leertaste** Mikro an/aus · **Esc** stoppen · **T** Texteingabe

## Installation per Docker (getrennt von der Hermes-VM) – empfohlen

```
Handy/PC ──NetBird──► Docker-Host: Caddy :443 ──► hermesvi :8800 ──LAN──► Hermes-VM :8642 / :8643
```

**Auf der Hermes-VM** (Schritte 1 und 2 unten, plus):

Hermes lauscht standardmäßig nur auf `127.0.0.1`. Damit der Container es erreicht, auf die interne IP der VM binden:

```sh
# ~/.hermes/profiles/<profil>/.env
API_SERVER_HOST=0.0.0.0
# ~/.hermes/config.yaml → plugins.entries.hermes-audio-api.settings.host: 0.0.0.0
```

Und per Firewall nur den Docker-Host durchlassen (Beispiel Docker-Host = 192.168.1.60):

```sh
sudo ufw allow from 192.168.1.60 to any port 8642,8643 proto tcp
sudo ufw deny 8642,8643/tcp
```

(Alternativ die Proxmox-Firewall für die VM nutzen.) Die Keys schützen zusätzlich.

**Auf dem Docker-Host:**

```sh
unzip hermesvi.zip && cd hermesvi
cp hermesvi.env.example hermesvi.env && nano hermesvi.env      # HERMES_URL/AUDIO_URL = IP der Hermes-VM, Keys eintragen
nano Caddyfile.docker                                         # NetBird-Name/IP des Docker-Hosts eintragen
docker compose up -d --build
docker compose logs -f hermesvi
curl -s http://127.0.0.1:8800/api/status                      # "hermes": true, "audio": true
```

Updates: neue Dateien drüberkopieren, `docker compose up -d --build`. Hermes-VM bleibt unberührt.
Ports 80/443 schon belegt (z. B. anderer Reverse-Proxy)? Dann den `caddy`-Dienst aus der Compose-Datei streichen und im vorhandenen Proxy auf `hermesvi:8800` bzw. `127.0.0.1:8800` zeigen – wichtig: Response-Buffering aus (Streaming).

## Installation direkt auf der Hermes-VM (Alternative ohne Docker)

### 1. API-Server des Agenten einschalten

In `~/.hermes/profiles/<profil>/.env` (bzw. `~/.hermes/.env`, falls der Agent das Standardprofil ist):

```sh
API_SERVER_ENABLED=true
API_SERVER_PORT=8642          # pro Profil ein eigener Port
API_SERVER_KEY=$(openssl rand -hex 24)
```

Gateway neu starten: `hermes -p <profil> gateway` (bzw. `hermes gateway`).
Test: `curl -H "Authorization: Bearer <KEY>" http://127.0.0.1:8642/v1/models` → sollte den Modellnamen deines Agenten zeigen (`API_SERVER_MODEL_NAME`).

### 2. Sprache – läuft standardmäßig im Container

Standard: Spracherkennung per ElevenLabs Scribe (`STT_BACKEND=elevenlabs`) und die ElevenLabs-Stimme deines Agenten – gleicher API-Key, gleiche `voice_id`, gleiches Modell wie in `~/.hermes` (Werte in `hermesvi.env` eintragen). **Das Hermes-Audio-Plugin wird nicht gebraucht** – es startet bei einem Gateway mit mehreren Profilen (Multiplexing) ohnehin nicht.

Optional, nur mit Einzelprofil-Gateway: über Hermes

```sh
hermes plugins install axAilotl/hermes-audio-api --enable
hermes config set AUDIO_API_KEY "$(openssl rand -hex 24)"
```

Gateway neu starten. Das Plugin nutzt die STT/TTS-Anbieter, die in deinem Hermes-Profil eingestellt sind
(z. B. `faster-whisper` lokal für Spracherkennung, ElevenLabs/OpenAI/Edge für die Stimme) – der Agent klingt dann überall gleich, auch in Telegram.
Für deutsche Erkennung die STT-Sprache in Hermes auf Deutsch stellen.

> Optional: lokale Spracherkennung (`STT_BACKEND=local`) bzw. kostenlose Edge-Stimme (`TTS_BACKEND=edge`) brauchen Zusatzpakete im Image:
> `docker compose build --build-arg EXTRA_PIP="faster-whisper edge-tts"`
> Die Spracherkennung läuft aber immer über das Plugin.

### 3. App installieren

```sh
sudo mkdir -p /opt/hermesvi && sudo cp -r . /opt/hermesvi && cd /opt/hermesvi
sudo python3 -m venv .venv && sudo .venv/bin/pip install -r requirements.txt
sudo cp hermesvi.env.example hermesvi.env && sudo nano hermesvi.env     # HERMES_KEY + AUDIO_KEY eintragen
sudo cp hermesvi.service /etc/systemd/system/                   # User= anpassen (der Hermes-User)
sudo systemctl daemon-reload && sudo systemctl enable --now hermesvi
curl http://127.0.0.1:8800/api/status
```

`/api/status` muss `"hermes": true` und `"audio": true` zeigen.

### 4. HTTPS (Pflicht fürs Mikrofon)

Browser geben das Mikrofon nur über HTTPS frei (Ausnahme: `localhost`). Mit NetBird zwei Wege – siehe `Caddyfile.example`:

- **A – `tls internal`:** Caddy erzeugt ein eigenes Zertifikat. Das Root-Zertifikat (`/var/lib/caddy/.local/share/caddy/pki/authorities/local/root.crt`) einmal auf Handy und PC als vertrauenswürdig installieren. Schnell, aber pro Gerät ein Schritt.
- **B – eigene Subdomain:** z. B. `hermesvi.deine-domain.de` → A-Record auf die NetBird-IP der VM. Zertifikat per DNS-Challenge (Caddy mit DNS-Plugin deines Providers). Danach funktioniert es auf jedem Gerät im NetBird-Netz ohne Extra-Schritt. **Empfohlen.**

Die App bleibt dabei nur im NetBird-Netz erreichbar – nichts hängt öffentlich im Internet.

### 5. Aufs Handy

Seite im Browser öffnen → „Zum Home-Bildschirm“. Startet dann wie eine App im Vollbild.

## Einstellungen im Panel (Tab „System“)

| Regler | Wirkung |
|---|---|
| Empfindlichkeit | Wie leise du sprechen darfst. Der Pegel-Balken zeigt deine Stimme, der gelbe Strich die Schwelle. |
| Pause | Wie lange Stille als „fertig gesprochen“ gilt. Kürzer = flotter, länger = du kannst nachdenken. |
| Sprechtempo | Geschwindigkeit der Stimme. |
| Unterbrechen | Reinreden stoppt den Agenten. Mit Lautsprecher ohne gute Echo-Unterdrückung ggf. ausschalten oder Kopfhörer nutzen. |

## Wenn was hakt

| Symptom | Ursache |
|---|---|
| Punkt oben links gelb, „Demo-Modus“ | Seite erreicht den Server nicht (z. B. als Datei geöffnet). |
| „Kein Mikrofon-Zugriff“ | Kein HTTPS oder Mikro im Browser verweigert. |
| „Spracherkennung lädt noch“ | Nur bei `STT_BACKEND=local`: Whisper-Modell wird beim ersten Start geladen – `docker compose logs hermesvi`, ein paar Minuten warten. |
| „Anfrage von fremder Seite abgelehnt“ | Schutz gegen fremde Webseiten (CSRF). Kommt das bei normaler Nutzung, setzt der Reverse-Proxy den `Host`-Header nicht durch – im NPM ist das Standard. |
| Stimme stumm | Edge-TTS braucht Internet vom Docker-Host. Alternativ `TTS_BACKEND=browser`. |
| Agent klingt anders als sonst / vergisst seine Rolle | `VOICE_HINT` leeren – die Responses-API gibt ihn als `instructions` mit. |
| Agent antwortet sich selbst | Echo vom Lautsprecher → Empfindlichkeit runter, Unterbrechen aus oder Kopfhörer. |
| Fehler 4xx im Verlauf bei `HERMES_MODE=responses` | Ältere Hermes-Version → `HERMES_MODE=chat`. |

`journalctl -u hermesvi -f` zeigt die Server-Logs.


## Desktop-Dashboard: Aufträge, Log und Chat

Ab 1300 px Fensterbreite zeigt die App drei Spalten: links **Aufträge** (2/3) und **Hermes-Log** (1/3), in der Mitte den Orb und darunter den **Chat** (tippen oder sprechen, Antworten auf Wunsch vorgelesen), rechts **Aktivität** und **System**. Am Handy bleibt alles wie gehabt; Aufträge und Log sind dort eigene Reiter im Panel.

Aufträge und Log holt die App direkt aus dem **Hermes-Dashboard** – auf der Hermes-VM läuft dafür kein Zusatzskript:

1. Auf der Hermes-VM einen Zugangs-Token für das Dashboard setzen, z. B. in `~/.hermes/.env`:

   ```sh
   HERMES_DASHBOARD_SESSION_TOKEN=$(python3 -c "import secrets;print(secrets.token_urlsafe(32))")
   ```
   (Wert direkt eintragen, nicht den Befehl.) Danach das Dashboard neu starten. Die Anmeldung per Benutzer/Passwort bleibt weiter möglich.

2. Vom Docker-Host testen:

   ```sh
   curl -s -H "Authorization: Bearer <TOKEN>" http://<hermes-vm>:9119/api/plugins/kanban/board | head -c 200
   ```

3. In `hermesvi.env`: `HERMES_DASHBOARD_URL` und `HERMES_DASHBOARD_TOKEN` eintragen → `docker compose up -d`.

Im Panel unter System zeigt „Aufträge & Log“, ob die Verbindung steht.
