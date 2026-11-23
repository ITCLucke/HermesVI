"""
HermesVI – schlanker Proxy zwischen Browser und Hermes Agent.

- liefert die Web-App (static/index.html) aus
- leitet Gespräche an den Hermes API-Server weiter (Responses- oder Chat-API)
- leitet Sprache an das hermes-audio-api Plugin weiter (STT + TTS)
- optional: Edge-TTS als kostenlose Stimme, falls das Audio-Plugin fehlt

Die Hermes-Keys bleiben auf dem Server, der Browser sieht sie nie.
"""
from __future__ import annotations

import base64
import json
import os
import secrets
import time
import uuid
from pathlib import Path

import httpx
from fastapi import FastAPI, File, Form, Request, UploadFile
from fastapi.responses import FileResponse, JSONResponse, Response, StreamingResponse

# ---------------------------------------------------------------- Konfiguration
def env(name: str, default: str = "") -> str:
    return os.environ.get(name, default).strip()

AGENT_NAME      = env("AGENT_NAME", "Hermes")
HERMES_URL      = env("HERMES_URL", "http://127.0.0.1:8642").rstrip("/")
HERMES_KEY      = env("HERMES_KEY")
HERMES_MODE     = env("HERMES_MODE", "responses")        # responses | chat
CONVERSATION    = env("HERMES_CONVERSATION", "hermesvi")
SESSION_KEY     = env("HERMES_SESSION_KEY") or CONVERSATION
AUDIO_URL       = env("AUDIO_URL", "http://127.0.0.1:8643").rstrip("/")
AUDIO_KEY       = env("AUDIO_KEY") or HERMES_KEY
TTS_BACKEND     = env("TTS_BACKEND", "elevenlabs")       # elevenlabs | edge | hermes | browser
# ElevenLabs – dieselben Werte wie in ~/.hermes/config.yaml des Agenten (tts.elevenlabs)
ELEVEN_KEY      = env("ELEVENLABS_API_KEY")
ELEVEN_VOICE    = env("ELEVENLABS_VOICE_ID", "pNInz6obpgDQGcFmaJgB")   # Hermes-Standard „Adam“
ELEVEN_MODEL    = env("ELEVENLABS_MODEL_ID", "eleven_multilingual_v2")
STT_BACKEND     = env("STT_BACKEND", "elevenlabs")       # elevenlabs (Scribe, schnell) | local (Whisper im Container) | hermes (Plugin)
ELEVEN_STT_MODEL = env("ELEVENLABS_STT_MODEL", "scribe_v2")
# Wie lange der Agent bei Sprachgesprächen nachdenkt: none | minimal | low | medium | high | leer = wie in Hermes
HERMES_REASONING = env("HERMES_REASONING", "low")
WHISPER_MODEL   = env("WHISPER_MODEL", "small")          # tiny | base | small | medium | large-v3
WHISPER_THREADS = int(env("WHISPER_THREADS", "4"))
EDGE_VOICE      = env("EDGE_VOICE", "de-DE-ConradNeural")
STT_LANGUAGE    = env("STT_LANGUAGE", "de")
VOICE_HINT      = env("VOICE_HINT", "Du sprichst gerade per Sprache. Antworte kurz, natürlich und gesprochen – keine Markdown-Listen, keine Codeblöcke, keine Emojis.")
APP_PASSWORD    = env("APP_PASSWORD")
# Ohne Passwort nur, wenn ausdrücklich gewollt (z. B. Zugangsschutz im Reverse-Proxy)
ALLOW_NO_AUTH   = env("ALLOW_NO_AUTH").lower() in ("1", "true", "yes", "ja")
# Optional: nur diese Hostnamen annehmen (Schutz gegen DNS-Rebinding), z. B. hermesvi.lan.example
ALLOWED_HOSTS   = {h.strip().lower() for h in env("ALLOWED_HOSTS").split(",") if h.strip()}
# Kanban-Meldungen: agent = Agent fasst das Ergebnis zusammen | announce = nur Titel + Status ansagen
NOTIFY_MODE     = env("NOTIFY_MODE", "agent") if env("NOTIFY_MODE", "agent") in ("agent", "announce") else "agent"
MAX_TEXT        = 64 * 1024            # Zeichen pro Nachricht
MAX_AUDIO       = 10 * 1024 * 1024     # Bytes pro Sprachaufnahme
MAX_BODY        = 12 * 1024 * 1024     # Bytes pro Anfrage
NOTIFY_TOKEN    = env("NOTIFY_TOKEN")      # nur für die optionale Brücke auf der Hermes-VM (POST /api/state)

# Aufträge + Log direkt aus dem Hermes-Dashboard (empfohlen, nichts auf der Hermes-VM nötig)
DASHBOARD_URL   = env("HERMES_DASHBOARD_URL").rstrip("/")
DASHBOARD_TOKEN = env("HERMES_DASHBOARD_TOKEN")
DASHBOARD_EVERY = int(env("DASHBOARD_INTERVAL", "15"))
LOG_NAME        = env("LOG_NAME", "gateway")      # gateway | agent | errors – leer = kein Log
LOG_LINES       = int(env("LOG_LINES", "80"))
NOTIFY_STATUSES = {x.strip() for x in env("NOTIFY_STATUSES", "done,failed,blocked").split(",") if x.strip()}   # leer = keine Ansagen
NOTIFY_ASSIGNEES = {x.strip() for x in env("NOTIFY_ASSIGNEES").split(",") if x.strip()}                     # leer = alle Agenten
LOG_SKIP        = env("LOG_SKIP", r"Native session startup recovery|receipt refused|kanban dispatcher: (holding|embedded)|Gateway housekeeping")
STATIC_DIR      = Path(__file__).parent / "static"

app = FastAPI(title="HermesVI", docs_url=None, redoc_url=None)
client = httpx.AsyncClient(timeout=httpx.Timeout(300.0, connect=5.0))

# ---------------------------------------------------------------- Lokale Spracherkennung
_whisper = None
_whisper_state = "off"


def _load_whisper():
    global _whisper, _whisper_state
    _whisper_state = "loading"
    try:
        from faster_whisper import WhisperModel   # nur im Image mit --build-arg EXTRA_PIP="faster-whisper"
        _whisper = WhisperModel(WHISPER_MODEL, device="cpu", compute_type="int8", cpu_threads=WHISPER_THREADS)
        _whisper_state = "ready"
    except Exception as e:  # Modell-Download oder Import fehlgeschlagen
        _whisper_state = f"error: {e}"[:200]
        print(f"[hermesvi] Whisper konnte nicht geladen werden: {e}", flush=True)


@app.on_event("startup")
async def _startup():
    if STT_BACKEND == "local":
        import threading
        threading.Thread(target=_load_whisper, daemon=True).start()


def _wav_to_array(audio: bytes):
    """WAV (PCM16) direkt einlesen und auf 16 kHz mono bringen – ohne PyAV/ffmpeg."""
    import io, wave
    import numpy as np
    with wave.open(io.BytesIO(audio), "rb") as w:
        ch, width, rate, n = w.getnchannels(), w.getsampwidth(), w.getframerate(), w.getnframes()
        frames = w.readframes(n)
    if width != 2:
        raise ValueError(f"WAV mit {width*8} Bit wird nicht unterstützt")
    x = np.frombuffer(frames, dtype="<i2").astype(np.float32) / 32768.0
    if ch > 1:
        x = x.reshape(-1, ch).mean(axis=1)
    if rate != 16000:
        t_new = np.arange(0, len(x) / rate, 1 / 16000)
        x = np.interp(t_new, np.arange(len(x)) / rate, x).astype(np.float32)
    return x


def _transcribe_local(audio: bytes) -> str:
    import io
    src = _wav_to_array(audio) if audio[:4] == b"RIFF" else io.BytesIO(audio)
    segments, _ = _whisper.transcribe(src, language=STT_LANGUAGE or None, beam_size=1,
                                      vad_filter=True, condition_on_previous_text=False)
    return " ".join(seg.text.strip() for seg in segments).strip()


# Verlauf nur für den Chat-Modus (Responses-Modus hält den Verlauf in Hermes)
_chat_history: dict[str, list[dict]] = {}


_MAX_SESSIONS = 20


def _history(session: str) -> list[dict]:
    if session not in _chat_history and len(_chat_history) >= _MAX_SESSIONS:
        _chat_history.pop(next(iter(_chat_history)))      # älteste Sitzung verwerfen
    return _chat_history.setdefault(session, [])


def hermes_headers(session: str | None = None) -> dict:
    h = {"Authorization": f"Bearer {HERMES_KEY}", "Content-Type": "application/json"}
    if session:
        # stabiler Gedächtnis-Scope, damit der Agent dich über Gespräche hinweg wiedererkennt
        h["X-Hermes-Session-Key"] = SESSION_KEY
    return h


# ---------------------------------------------------------------- Schutz gegen fremde Webseiten (CSRF)
# Eine fremde Seite im selben Browser darf dem Agenten keine Befehle schicken. Browser senden bei
# jeder Anfrage von einer anderen Seite den Herkunfts-Header (Origin / Sec-Fetch-Site) mit.
_SAFE_METHODS = {"GET", "HEAD", "OPTIONS"}


def _req_host(request: Request) -> str:
    return (request.headers.get("x-forwarded-host") or request.headers.get("host") or "").split(",")[0].strip().lower()


def _same_origin(request: Request) -> bool:
    site = request.headers.get("sec-fetch-site")
    if site and site not in ("same-origin", "none"):
        return False
    origin = request.headers.get("origin")
    if origin and origin != "null":
        from urllib.parse import urlparse
        if urlparse(origin).netloc.lower() != _req_host(request):
            return False
    elif origin == "null":
        return False
    return True


def _is_bridge(request: Request) -> bool:
    """Brücke auf der Hermes-VM: nur POST /api/state, hat ein eigenes Token."""
    return request.method == "POST" and request.url.path == "/api/state"


@app.middleware("http")
async def csrf_guard(request: Request, call_next):
    path = request.url.path
    if request.method not in _SAFE_METHODS and path.startswith("/api/") and not _is_bridge(request):
        if not _same_origin(request):
            return JSONResponse({"error": "Anfrage von fremder Seite abgelehnt"}, status_code=403)
        ctype = request.headers.get("content-type", "")
        if path != "/api/stt" and not ctype.startswith("application/json"):
            return JSONResponse({"error": "application/json erwartet"}, status_code=415)
    return await call_next(request)


# ---------------------------------------------------------------- Zugangsschutz
_fails: dict[str, list[float]] = {}     # Fehlversuche pro Client
_FAIL_LIMIT, _FAIL_WINDOW = 10, 900     # 10 Fehlversuche in 15 Minuten → 15 Minuten gesperrt


def _client_ip(request: Request) -> str:
    # hinter einem Reverse-Proxy steht die echte Adresse als letzter Eintrag in X-Forwarded-For
    xff = request.headers.get("x-forwarded-for", "")
    return (xff.split(",")[-1].strip() if xff else "") or (request.client.host if request.client else "?")


_NO_AUTH_PAGE = """<!doctype html><meta charset="utf-8"><title>HermesVI – Zugangsschutz fehlt</title>
<body style="font:16px system-ui;background:#05080d;color:#dbe7f0;max-width:640px;margin:60px auto;padding:0 20px">
<h2>Zugangsschutz fehlt</h2><p>Ohne Schutz könnte jedes Gerät im Netz deinem Agenten Befehle geben.</p>
<p>In <code>hermesvi.env</code> eines von beiden setzen und den Container neu starten:</p>
<ul><li><code>APP_PASSWORD=…</code> – Passwortabfrage durch HermesVI, oder</li>
<li><code>ALLOW_NO_AUTH=true</code> – nur, wenn dein Reverse-Proxy schon schützt (z. B. Access List im Nginx Proxy Manager).</li></ul></body>"""


@app.middleware("http")
async def access_guard(request: Request, call_next):
    path = request.url.path
    if ALLOWED_HOSTS and path != "/health" and _req_host(request).rsplit(":", 1)[0] not in ALLOWED_HOSTS:
        return JSONResponse({"error": "unbekannter Hostname"}, status_code=421)
    cl = request.headers.get("content-length")
    if cl and cl.isdigit() and int(cl) > MAX_BODY:
        return JSONResponse({"error": "Anfrage zu groß"}, status_code=413)
    if path == "/health" or _is_bridge(request):
        return await call_next(request)
    if not APP_PASSWORD:
        if ALLOW_NO_AUTH:
            return await call_next(request)
        if path.startswith("/api/"):
            return JSONResponse({"error": "Zugangsschutz fehlt: APP_PASSWORD oder ALLOW_NO_AUTH=true setzen"}, status_code=503)
        return Response(_NO_AUTH_PAGE, status_code=503, media_type="text/html; charset=utf-8")
    ip, now = _client_ip(request), time.time()
    recent = [t for t in _fails.get(ip, []) if now - t < _FAIL_WINDOW]
    if len(recent) >= _FAIL_LIMIT:
        return Response("Zu viele Fehlversuche – bitte später erneut versuchen.", status_code=429,
                        headers={"Retry-After": str(_FAIL_WINDOW)})
    auth = request.headers.get("authorization", "")
    ok = False
    if auth.lower().startswith("basic "):
        try:
            _, pw = base64.b64decode(auth[6:]).decode().split(":", 1)
            ok = secrets.compare_digest(pw.encode(), APP_PASSWORD.encode())
        except Exception:
            ok = False
    if not ok:
        if auth:                                  # erster Aufruf ohne Daten zählt nicht als Fehlversuch
            recent.append(now)
        _fails[ip] = recent
        if len(_fails) > 5000:
            _fails.clear()
        return Response(status_code=401, headers={"WWW-Authenticate": 'Basic realm="HermesVI"'})
    _fails.pop(ip, None)
    return await call_next(request)


# ---------------------------------------------------------------- Sicherheits-Header
_CSP = ("default-src 'self'; script-src 'self' 'unsafe-inline'; style-src 'self' 'unsafe-inline'; "
        "img-src 'self' data: blob:; media-src 'self' data: blob:; connect-src 'self'; font-src 'self' data:; "
        "object-src 'none'; base-uri 'none'; form-action 'self'; frame-ancestors 'none'")


@app.middleware("http")
async def security_headers(request: Request, call_next):
    resp = await call_next(request)
    resp.headers.setdefault("Content-Security-Policy", _CSP)
    resp.headers.setdefault("X-Frame-Options", "DENY")
    resp.headers.setdefault("X-Content-Type-Options", "nosniff")
    resp.headers.setdefault("Referrer-Policy", "no-referrer")
    resp.headers.setdefault("Permissions-Policy", "microphone=(self), camera=(self), geolocation=()")
    return resp


# ---------------------------------------------------------------- Seiten
@app.get("/")
async def index():
    return FileResponse(STATIC_DIR / "index.html", headers={"Cache-Control": "no-cache"})


@app.get("/manifest.webmanifest")
async def manifest():
    return JSONResponse({
        "name": AGENT_NAME, "short_name": AGENT_NAME, "start_url": "/", "display": "standalone",
        "background_color": "#05080d", "theme_color": "#05080d",
        "icons": [{"src": "/icon.svg", "sizes": "any", "type": "image/svg+xml"}],
    })


@app.get("/icon.svg")
async def icon():
    svg = ('<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 100 100"><rect width="100" height="100" fill="#05080d"/>'
           '<circle cx="50" cy="50" r="30" fill="none" stroke="#3ee0ff" stroke-width="5"/>'
           '<circle cx="50" cy="50" r="14" fill="#3ee0ff"/></svg>')
    return Response(svg, media_type="image/svg+xml")


@app.get("/health")
async def health():
    return {"ok": True}


@app.get("/api/status")
async def status():
    out = {"name": AGENT_NAME, "mode": HERMES_MODE, "tts": TTS_BACKEND, "stt": STT_BACKEND,
           "hermes": False, "audio": False, "model": None, "notify_mode": NOTIFY_MODE,
           "auth": "password" if APP_PASSWORD else "proxy"}
    t0 = time.perf_counter()
    try:
        r = await client.get(f"{HERMES_URL}/health", timeout=3)
        out["hermes"] = r.status_code == 200
        out["latency_ms"] = round((time.perf_counter() - t0) * 1000)
        m = await client.get(f"{HERMES_URL}/v1/models", headers=hermes_headers(), timeout=3)
        if m.status_code == 200:
            data = m.json().get("data") or []
            out["model"] = data[0]["id"] if data else None
    except Exception as e:
        out["hermes_error"] = str(e)[:200]
    plugin_ok = False
    if STT_BACKEND == "hermes" or TTS_BACKEND == "hermes":
        try:
            r = await client.get(f"{AUDIO_URL}/health", timeout=3)
            plugin_ok = r.status_code == 200
        except Exception:
            pass
    stt_ok = (_whisper_state == "ready") if STT_BACKEND == "local" else (bool(ELEVEN_KEY) if STT_BACKEND == "elevenlabs" else plugin_ok)
    out["reasoning"] = HERMES_REASONING or "hermes"
    out["lagebild"] = "dashboard" if DASHBOARD_URL and DASHBOARD_TOKEN else ("bruecke" if NOTIFY_TOKEN else "aus")
    if _state.get("error"):
        out["lagebild_error"] = _state["error"]
    tts_ok = plugin_ok if TTS_BACKEND == "hermes" else (bool(ELEVEN_KEY) if TTS_BACKEND == "elevenlabs" else True)
    out["audio"] = stt_ok and tts_ok
    if STT_BACKEND == "local":
        out["whisper"] = f"{WHISPER_MODEL}: {_whisper_state}"
    return out


# ---------------------------------------------------------------- Gespräch
def sse(obj: dict) -> bytes:
    return f"data: {json.dumps(obj, ensure_ascii=False)}\n\n".encode()


async def iter_sse(resp: httpx.Response):
    """Liefert (event, data) Paare aus einem SSE-Stream."""
    event, data_lines = None, []
    async for line in resp.aiter_lines():
        if line == "":
            if data_lines:
                yield event, "\n".join(data_lines)
            event, data_lines = None, []
            continue
        if line.startswith(":"):
            continue  # keepalive
        if line.startswith("event:"):
            event = line[6:].strip()
        elif line.startswith("data:"):
            data_lines.append(line[5:].lstrip())
    if data_lines:
        yield event, "\n".join(data_lines)


async def stream_responses(text: str, session: str):
    body = {
        "model": "hermes-agent",
        "input": text,
        "conversation": f"{CONVERSATION}-{session}" if session != "main" else CONVERSATION,
        "instructions": VOICE_HINT,
        "stream": True,
    }
    if HERMES_REASONING:
        body["model_options"] = {"reasoning_effort": HERMES_REASONING}
    async with client.stream("POST", f"{HERMES_URL}/v1/responses", headers=hermes_headers(session), json=body) as r:
        if r.status_code != 200:
            yield sse({"type": "error", "message": f"Hermes antwortet mit {r.status_code}: {(await r.aread())[:300].decode(errors='ignore')}"})
            return
        async for event, data in iter_sse(r):
            if data == "[DONE]":
                break
            try:
                obj = json.loads(data)
            except json.JSONDecodeError:
                continue
            etype = obj.get("type") or event or ""
            if etype == "response.output_text.delta":
                yield sse({"type": "delta", "text": obj.get("delta", "")})
            elif etype == "response.output_item.added":
                item = obj.get("item") or {}
                if item.get("type") == "function_call":
                    yield sse({"type": "tool", "name": item.get("name", "tool"), "preview": str(item.get("arguments", ""))[:160]})
            elif etype == "response.output_item.done":
                item = obj.get("item") or {}
                if item.get("type") == "function_call_output":
                    yield sse({"type": "tool_done", "preview": str(item.get("output", ""))[:160]})
            elif etype in ("response.failed", "error"):
                msg = (obj.get("response") or {}).get("error") or obj.get("error") or obj
                yield sse({"type": "error", "message": str(msg)[:300]})
            elif etype == "response.completed":
                break


async def stream_chat(text: str, session: str):
    hist = _history(session)
    hist.append({"role": "user", "content": text})
    messages = [{"role": "system", "content": VOICE_HINT}] + hist[-40:]
    body = {"model": "hermes-agent", "messages": messages, "stream": True}
    if HERMES_REASONING:
        body["model_options"] = {"reasoning_effort": HERMES_REASONING}
    answer = []
    async with client.stream("POST", f"{HERMES_URL}/v1/chat/completions", headers=hermes_headers(session), json=body) as r:
        if r.status_code != 200:
            hist.pop()
            yield sse({"type": "error", "message": f"Hermes antwortet mit {r.status_code}: {(await r.aread())[:300].decode(errors='ignore')}"})
            return
        async for event, data in iter_sse(r):
            if data == "[DONE]":
                break
            try:
                obj = json.loads(data)
            except json.JSONDecodeError:
                continue
            if event == "hermes.tool.progress":
                name = obj.get("tool") or obj.get("name") or "tool"
                prev = obj.get("preview") or obj.get("message") or ""
                yield sse({"type": "tool", "name": name, "preview": str(prev)[:160]})
                continue
            for ch in obj.get("choices") or []:
                delta = (ch.get("delta") or {}).get("content")
                if delta:
                    answer.append(delta)
                    yield sse({"type": "delta", "text": delta})
    hist.append({"role": "assistant", "content": "".join(answer)})
    del hist[:-80]


@app.post("/api/chat")
async def chat(request: Request):
    payload = await request.json()
    if not isinstance(payload, dict):
        return JSONResponse({"error": "ungültig"}, status_code=400)
    text = str(payload.get("text") or "").strip()
    session = str(payload.get("session") or "main")[:64]
    if not text:
        return JSONResponse({"error": "leer"}, status_code=400)
    if len(text) > MAX_TEXT:
        return JSONResponse({"error": f"Nachricht zu lang (max. {MAX_TEXT // 1024} KB)"}, status_code=413)

    async def gen():
        yield sse({"type": "start", "id": uuid.uuid4().hex[:8]})
        try:
            src = stream_responses if HERMES_MODE == "responses" else stream_chat
            async for chunk in src(text, session):
                yield chunk
        except httpx.HTTPError as e:
            yield sse({"type": "error", "message": f"Hermes nicht erreichbar ({e.__class__.__name__})"})
        yield sse({"type": "done"})

    return StreamingResponse(gen(), media_type="text/event-stream",
                             headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})


@app.post("/api/reset")
async def reset(request: Request):
    payload = await request.json()
    _chat_history.pop(str((payload or {}).get("session") or "main")[:64], None)
    return {"ok": True}


# ---------------------------------------------------------------- Sprache
@app.post("/api/stt")
async def stt(file: UploadFile = File(...)):
    audio = await file.read(MAX_AUDIO + 1)
    if len(audio) > MAX_AUDIO:
        return JSONResponse({"error": "Aufnahme zu lang"}, status_code=413)
    if STT_BACKEND == "elevenlabs":
        try:
            r = await client.post("https://api.elevenlabs.io/v1/speech-to-text",
                                  headers={"xi-api-key": ELEVEN_KEY},
                                  data={"model_id": ELEVEN_STT_MODEL, "language_code": STT_LANGUAGE or "",
                                        "tag_audio_events": "false"},
                                  files={"file": ("speech.wav", audio, "audio/wav")}, timeout=60)
        except httpx.HTTPError as e:
            return JSONResponse({"error": f"ElevenLabs nicht erreichbar ({e.__class__.__name__})"}, status_code=502)
        if r.status_code != 200:
            return JSONResponse({"error": f"ElevenLabs STT {r.status_code}: {r.text[:300]}"}, status_code=502)
        return {"text": (r.json().get("text") or "").strip(), "filtered": False}
    if STT_BACKEND == "local":
        if _whisper_state != "ready":
            msg = "Spracherkennung lädt noch – gleich nochmal" if _whisper_state == "loading" else f"Whisper: {_whisper_state}"
            return JSONResponse({"error": msg}, status_code=503)
        from starlette.concurrency import run_in_threadpool
        try:
            text = await run_in_threadpool(_transcribe_local, audio)
        except Exception as e:
            print(f"[hermesvi] STT-Fehler: {e!r}", flush=True)
            return JSONResponse({"error": f"Spracherkennung fehlgeschlagen: {e}"[:300]}, status_code=500)
        return {"text": text, "filtered": False}
    files = {"file": (file.filename or "speech.wav", audio, file.content_type or "audio/wav")}
    data = {"response_format": "json", "language": STT_LANGUAGE}
    try:
        r = await client.post(f"{AUDIO_URL}/v1/audio/transcriptions",
                              headers={"Authorization": f"Bearer {AUDIO_KEY}"}, files=files, data=data, timeout=60)
    except httpx.HTTPError as e:
        return JSONResponse({"error": f"Audio-Plugin nicht erreichbar ({e.__class__.__name__})"}, status_code=502)
    if r.status_code != 200:
        return JSONResponse({"error": r.text[:300]}, status_code=502)
    text = r.json().get("text", "") if "json" in r.headers.get("content-type", "") else r.text
    return {"text": text.strip(), "filtered": r.headers.get("X-Hermes-Transcript-Filtered") == "true"}


@app.post("/api/tts")
async def tts(request: Request):
    payload = await request.json()
    text = str(payload.get("text") or "").strip()[:4000]
    try:
        speed = max(0.5, min(2.0, float(payload.get("speed") or 1.0)))
    except (TypeError, ValueError):
        speed = 1.0
    if speed != speed:                      # NaN
        speed = 1.0
    if not text:
        return Response(status_code=204)

    if TTS_BACKEND == "elevenlabs":
        body = {"text": text, "model_id": ELEVEN_MODEL}
        if abs(speed - 1.0) > 0.01:
            body["voice_settings"] = {"speed": max(0.7, min(1.2, speed))}
        try:
            r = await client.post(f"https://api.elevenlabs.io/v1/text-to-speech/{ELEVEN_VOICE}",
                                  params={"output_format": "mp3_44100_128"},
                                  headers={"xi-api-key": ELEVEN_KEY, "Content-Type": "application/json"},
                                  json=body, timeout=60)
        except httpx.HTTPError as e:
            return JSONResponse({"error": f"ElevenLabs nicht erreichbar ({e.__class__.__name__})"}, status_code=502)
        if r.status_code != 200:
            print(f"[hermesvi] ElevenLabs TTS {r.status_code}: {r.text[:200]}", flush=True)
            code = 429 if r.status_code == 429 else 502
            return JSONResponse({"error": f"ElevenLabs {r.status_code}: {r.text[:300]}"}, status_code=code)
        return Response(r.content, media_type="audio/mpeg")

    if TTS_BACKEND == "edge":
        try:
            import edge_tts  # nur im Image mit --build-arg EXTRA_PIP="edge-tts"
        except ImportError:
            return JSONResponse({"error": "Edge-TTS ist nicht installiert (EXTRA_PIP=edge-tts)"}, status_code=501)
        rate = f"{round((speed - 1) * 100):+d}%"
        com = edge_tts.Communicate(text, EDGE_VOICE, rate=rate)
        buf = bytearray()
        async for chunk in com.stream():
            if chunk["type"] == "audio":
                buf.extend(chunk["data"])
        return Response(bytes(buf), media_type="audio/mpeg")

    try:
        r = await client.post(f"{AUDIO_URL}/v1/audio/speech",
                              headers={"Authorization": f"Bearer {AUDIO_KEY}", "Content-Type": "application/json"},
                              json={"input": text, "response_format": "mp3", "speed": speed}, timeout=60)
    except httpx.HTTPError as e:
        return JSONResponse({"error": f"Audio-Plugin nicht erreichbar ({e.__class__.__name__})"}, status_code=502)
    if r.status_code != 200:
        return JSONResponse({"error": r.text[:300]}, status_code=502)
    return Response(r.content, media_type=r.headers.get("content-type", "audio/mpeg"))


# ---------------------------------------------------------------- Lagebild: offene Aufträge + Hermes-Log
_state: dict = {"ts": 0, "tasks": [], "logs": [], "source": None, "error": None}
_FINISHED = {"done", "failed", "cancelled", "archived"}
_TASK_KEYS = ("id", "title", "assignee", "status", "started_at", "created_at", "priority")
_notes: list[dict] = []
_note_seq = 0


def _clean_tasks(tasks):
    return [{k: (str(t.get(k))[:300] if t.get(k) is not None else None) for k in _TASK_KEYS}
            for t in tasks[:200] if isinstance(t, dict)]


async def _dashboard_loop():
    global _note_seq
    import asyncio, re
    skip = re.compile(LOG_SKIP) if LOG_SKIP else None
    hdr = {"Authorization": f"Bearer {DASHBOARD_TOKEN}"}
    known: dict | None = None      # erster Durchlauf merkt sich nur den Stand
    while True:
        try:
            r = await client.get(f"{DASHBOARD_URL}/api/plugins/kanban/board", headers=hdr, timeout=20)
            if r.status_code != 200:
                raise RuntimeError(f"Kanban HTTP {r.status_code}: {r.text[:120]}")
            tasks = [t for col in (r.json().get("columns") or []) for t in (col.get("tasks") or [])]
            now = {str(t.get("id")): str(t.get("status")) for t in tasks}
            if known is not None and NOTIFY_STATUSES:
                for t in tasks:
                    tid, st = str(t.get("id")), str(t.get("status"))
                    if st not in NOTIFY_STATUSES or known.get(tid) == st:
                        continue
                    if NOTIFY_ASSIGNEES and str(t.get("assignee") or "") not in NOTIFY_ASSIGNEES:
                        continue
                    result = t.get("result") or t.get("latest_summary") or ""
                    try:
                        d = await client.get(f"{DASHBOARD_URL}/api/plugins/kanban/tasks/{tid}", headers=hdr, timeout=20)
                        if d.status_code == 200:
                            full = d.json().get("task") or {}
                            result = full.get("result") or full.get("latest_summary") or result
                    except Exception:
                        pass
                    _note_seq += 1
                    _notes.append({"seq": _note_seq, "ts": int(time.time()), "id": tid, "title": str(t.get("title") or "")[:300],
                                   "assignee": str(t.get("assignee") or "")[:64], "status": st, "result": str(result)[:2500]})
                    del _notes[:-100]
            known = now
            logs: list[str] = []
            if LOG_NAME:
                lr = await client.get(f"{DASHBOARD_URL}/api/logs", headers=hdr, timeout=20,
                                      params={"file": LOG_NAME, "lines": min(500, LOG_LINES * 2)})
                if lr.status_code == 200:
                    logs = [l.rstrip("\n") for l in (lr.json().get("lines") or [])]
                    logs = [l for l in logs if l.strip() and not (skip and skip.search(l))][-LOG_LINES:]
            _state.update({"ts": int(time.time()), "source": "dashboard", "error": None, "logs": logs,
                           "tasks": _clean_tasks([t for t in tasks if t.get("status") not in _FINISHED])})
        except Exception as e:
            _state["error"] = f"Dashboard: {e}"[:200]
            print(f"[hermesvi] Dashboard-Abfrage fehlgeschlagen: {e}", flush=True)
        await asyncio.sleep(DASHBOARD_EVERY)


@app.on_event("startup")
async def _start_dashboard():
    if DASHBOARD_URL and DASHBOARD_TOKEN:
        import asyncio
        asyncio.create_task(_dashboard_loop())


@app.post("/api/state")
async def post_state(request: Request):
    """Alternative Quelle: Brücke auf der Hermes-VM schickt Aufträge + Log."""
    if not NOTIFY_TOKEN or not secrets.compare_digest(request.headers.get("authorization", "").encode(),
                                                     f"Bearer {NOTIFY_TOKEN}".encode()):
        return JSONResponse({"error": "unauthorized"}, status_code=401)
    payload = await request.json()
    if not isinstance(payload, dict):
        return JSONResponse({"error": "ungültig"}, status_code=400)
    tasks = payload.get("tasks") if isinstance(payload.get("tasks"), list) else []
    logs = payload.get("logs") if isinstance(payload.get("logs"), list) else []
    _state.update({"ts": int(time.time()), "source": str(payload.get("source") or "")[:64], "error": None,
                   "tasks": _clean_tasks([t for t in tasks if isinstance(t, dict) and t.get("status") not in _FINISHED]),
                   "logs": [str(l)[:500] for l in logs[-150:]]})
    return {"ok": True}


@app.get("/api/notifications")
async def notifications(after: int = -1):
    if after < 0:
        return {"seq": _note_seq, "items": []}
    return {"seq": _note_seq, "items": [{k: v for k, v in n.items() if k != "claimed"} for n in _notes if n["seq"] > after]}


@app.post("/api/notifications/claim")
async def claim_notification(request: Request):
    """Jede Meldung geht nur an EIN Gerät weiter – sonst arbeitet der Agent bei mehreren offenen Geräten doppelt."""
    payload = await request.json()
    try:
        seq = int((payload or {}).get("seq"))
    except (TypeError, ValueError):
        return JSONResponse({"error": "seq fehlt"}, status_code=400)
    for n in _notes:
        if n["seq"] == seq:
            if n.get("claimed"):
                return {"ok": False}
            n["claimed"] = True
            return {"ok": True}
    return {"ok": False}


@app.get("/api/state")
async def get_state():
    return {**_state, "age": (int(time.time()) - _state["ts"]) if _state["ts"] else None}


@app.get("/api/config")
async def config():
    return {"name": AGENT_NAME, "tts": TTS_BACKEND, "notify_mode": NOTIFY_MODE}


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host=env("HOST", "127.0.0.1"), port=int(env("PORT", "8800")))
