// HermesVI Desktop – lokaler Mini-Server (ersetzt den Docker-Container auf dem PC).
// Läuft nur auf 127.0.0.1, spricht direkt mit Hermes, ElevenLabs und dem Hermes-Dashboard.
// Keine Abhängigkeiten außer Node (fetch, FormData, Blob sind eingebaut).
"use strict";
const http = require("http");
const fs = require("fs");
const path = require("path");

const UI_DIR = path.join(__dirname, "ui");
const FINISHED = new Set(["done", "failed", "cancelled", "archived"]);
const TASK_KEYS = ["id", "title", "assignee", "status", "started_at", "created_at", "priority"];
const MAX_TEXT = 64 * 1024, MAX_BODY = 12 * 1024 * 1024, MAX_SESSIONS = 20;
const SEC_HEADERS = {
  "Content-Security-Policy": "default-src 'self'; script-src 'self' 'unsafe-inline'; style-src 'self' 'unsafe-inline'; " +
    "img-src 'self' data: blob:; media-src 'self' data: blob:; connect-src 'self'; font-src 'self' data:; " +
    "object-src 'none'; base-uri 'none'; form-action 'self'; frame-ancestors 'none'",
  "X-Frame-Options": "DENY", "X-Content-Type-Options": "nosniff", "Referrer-Policy": "no-referrer",
};
const DEFAULT_HINT = (user) =>
  `Du sprichst gerade per Sprache${user ? " mit " + user : ""}. Antworte kurz, natürlich und gesprochen – keine Markdown-Listen, keine Codeblöcke, keine Emojis.`;

function createServer(getConfig, hooks = {}) {
  const state = { ts: 0, tasks: [], logs: [], source: null, error: null };
  const notes = []; let noteSeq = 0; let known = null;   // Kanban-Meldungen
  const chatHistory = new Map();
  let dashTimer = null;

  const C = () => {
    const c = getConfig();
    return {
      agentName: c.agentName || "Hermes",
      userName: c.userName || "",
      hermesUrl: (c.hermesUrl || "").replace(/\/+$/, ""),
      hermesKey: c.secrets?.hermesKey || "",
      hermesMode: c.hermesMode || "responses",
      conversation: c.conversation || "hermesvi-pc",
      reasoning: c.reasoning ?? "low",
      voiceHint: c.voiceHint || DEFAULT_HINT(c.userName),
      sttBackend: c.sttBackend || "elevenlabs",
      ttsBackend: c.ttsBackend || "elevenlabs",
      sttLanguage: c.sttLanguage || "de",
      elevenKey: c.secrets?.elevenKey || "",
      elevenVoice: c.elevenVoice || "pNInz6obpgDQGcFmaJgB",
      elevenModel: c.elevenModel || "eleven_flash_v2_5",
      elevenSttModel: c.elevenSttModel || "scribe_v2",
      audioUrl: (c.audioUrl || "").replace(/\/+$/, ""),
      audioKey: c.secrets?.audioKey || c.secrets?.hermesKey || "",
      dashboardUrl: (c.dashboardUrl || "").replace(/\/+$/, ""),
      dashboardToken: c.secrets?.dashboardToken || "",
      dashboardInterval: Math.max(5, Number(c.dashboardInterval) || 15),
      logName: c.logName ?? "gateway",
      logLines: Math.max(10, Number(c.logLines) || 80),
      logSkip: c.logSkip ?? "Native session startup recovery|receipt refused|kanban dispatcher: (holding|embedded)|Gateway housekeeping",
      notifyEnabled: c.notifyEnabled ?? true,
      notifyMode: c.notifyMode === "announce" ? "announce" : "agent",
      notifyStatuses: new Set(String(c.notifyStatuses ?? "done,failed,blocked").split(",").map((x) => x.trim()).filter(Boolean)),
      notifyAssignees: new Set(String(c.notifyAssignees ?? "").split(",").map((x) => x.trim()).filter(Boolean)),
    };
  };

  // ------------------------------------------------------------ Hilfen
  const send = (res, code, body, type = "application/json") => {
    const data = typeof body === "string" || Buffer.isBuffer(body) ? body : JSON.stringify(body);
    res.writeHead(code, { "Content-Type": type, "Cache-Control": "no-store", ...SEC_HEADERS });
    res.end(data);
  };
  const readBody = (req) => new Promise((resolve, reject) => {
    const chunks = []; let size = 0;
    req.on("data", (c) => { size += c.length; if (size > MAX_BODY) { reject(new Error("zu groß")); req.destroy(); } else chunks.push(c); });
    req.on("end", () => resolve(Buffer.concat(chunks)));
    req.on("error", reject);
  });
  const hermesHeaders = (c) => ({ Authorization: `Bearer ${c.hermesKey}`, "Content-Type": "application/json", "X-Hermes-Session-Key": c.conversation });
  const timeout = (ms) => AbortSignal.timeout(ms);

  async function* sseEvents(response) {
    const reader = response.body.getReader(); const dec = new TextDecoder();
    let buf = "", event = null, data = [];
    for (;;) {
      const { value, done } = await reader.read();
      if (done) break;
      buf += dec.decode(value, { stream: true });
      let i;
      while ((i = buf.indexOf("\n")) >= 0) {
        let line = buf.slice(0, i); buf = buf.slice(i + 1);
        if (line.endsWith("\r")) line = line.slice(0, -1);
        if (line === "") { if (data.length) yield [event, data.join("\n")]; event = null; data = []; continue; }
        if (line.startsWith(":")) continue;
        if (line.startsWith("event:")) event = line.slice(6).trim();
        else if (line.startsWith("data:")) data.push(line.slice(5).replace(/^ /, ""));
      }
    }
    if (data.length) yield [event, data.join("\n")];
  }

  // ------------------------------------------------------------ Gespräch
  async function streamChat(res, text, session) {
    const c = C();
    const out = (o) => res.write(`data: ${JSON.stringify(o)}\n\n`);
    res.writeHead(200, { "Content-Type": "text/event-stream", "Cache-Control": "no-cache", ...SEC_HEADERS });
    out({ type: "start" });
    try {
      if (!c.hermesUrl || !c.hermesKey) throw new Error("Hermes ist noch nicht eingerichtet (Einstellungen)");
      if (c.hermesMode === "responses") {
        const body = { model: "hermes-agent", input: text, conversation: session === "main" ? c.conversation : `${c.conversation}-${session}`,
          instructions: c.voiceHint, stream: true };
        if (c.reasoning) body.model_options = { reasoning_effort: c.reasoning };
        const r = await fetch(`${c.hermesUrl}/v1/responses`, { method: "POST", headers: hermesHeaders(c), body: JSON.stringify(body) });
        if (!r.ok) throw new Error(`Hermes antwortet mit ${r.status}: ${(await r.text()).slice(0, 300)}`);
        for await (const [event, data] of sseEvents(r)) {
          if (data === "[DONE]") break;
          let o; try { o = JSON.parse(data); } catch { continue; }
          const t = o.type || event || "";
          if (t === "response.output_text.delta") out({ type: "delta", text: o.delta || "" });
          else if (t === "response.output_item.added" && o.item?.type === "function_call")
            out({ type: "tool", name: o.item.name || "tool", preview: String(o.item.arguments || "").slice(0, 160) });
          else if (t === "response.output_item.done" && o.item?.type === "function_call_output")
            out({ type: "tool_done", preview: String(o.item.output || "").slice(0, 160) });
          else if (t === "response.failed" || t === "error") out({ type: "error", message: JSON.stringify(o.response?.error || o.error || o).slice(0, 300) });
          else if (t === "response.completed") break;
        }
      } else {
        if (!chatHistory.has(session) && chatHistory.size >= MAX_SESSIONS) chatHistory.delete(chatHistory.keys().next().value);
        const hist = chatHistory.get(session) || []; chatHistory.set(session, hist);
        hist.push({ role: "user", content: text });
        const body = { model: "hermes-agent", stream: true, messages: [{ role: "system", content: c.voiceHint }, ...hist.slice(-40)] };
        if (c.reasoning) body.model_options = { reasoning_effort: c.reasoning };
        const r = await fetch(`${c.hermesUrl}/v1/chat/completions`, { method: "POST", headers: hermesHeaders(c), body: JSON.stringify(body) });
        if (!r.ok) { hist.pop(); throw new Error(`Hermes antwortet mit ${r.status}: ${(await r.text()).slice(0, 300)}`); }
        let answer = "";
        for await (const [event, data] of sseEvents(r)) {
          if (data === "[DONE]") break;
          let o; try { o = JSON.parse(data); } catch { continue; }
          if (event === "hermes.tool.progress") { out({ type: "tool", name: o.tool || o.name || "tool", preview: String(o.preview || o.message || "").slice(0, 160) }); continue; }
          for (const ch of o.choices || []) { const d = ch.delta?.content; if (d) { answer += d; out({ type: "delta", text: d }); } }
        }
        hist.push({ role: "assistant", content: answer });
        if (hist.length > 80) hist.splice(0, hist.length - 80);
      }
    } catch (e) {
      out({ type: "error", message: e.cause?.code ? `Hermes nicht erreichbar (${e.cause.code})` : String(e.message || e) });
    }
    out({ type: "done" });
    res.end();
  }

  // ------------------------------------------------------------ Sprache
  async function stt(req, res) {
    const c = C();
    const raw = await readBody(req);
    const form = await new Request("http://x/", { method: "POST", headers: { "content-type": req.headers["content-type"] }, body: raw }).formData();
    const file = form.get("file");
    if (!file) return send(res, 400, { error: "keine Aufnahme" });
    try {
      if (c.sttBackend === "elevenlabs") {
        if (!c.elevenKey) return send(res, 503, { error: "ElevenLabs-Key fehlt (Einstellungen)" });
        const fd = new FormData();
        fd.append("model_id", c.elevenSttModel); fd.append("language_code", c.sttLanguage); fd.append("tag_audio_events", "false");
        fd.append("file", file, "speech.wav");
        const r = await fetch("https://api.elevenlabs.io/v1/speech-to-text", { method: "POST", headers: { "xi-api-key": c.elevenKey }, body: fd, signal: timeout(60000) });
        const t = await r.text();
        if (!r.ok) return send(res, 502, { error: `ElevenLabs STT ${r.status}: ${t.slice(0, 300)}` });
        return send(res, 200, { text: (JSON.parse(t).text || "").trim() });
      }
      const fd = new FormData(); fd.append("file", file, "speech.wav"); fd.append("response_format", "json");
      const r = await fetch(`${c.audioUrl}/v1/audio/transcriptions`, { method: "POST", headers: { Authorization: `Bearer ${c.audioKey}` }, body: fd, signal: timeout(60000) });
      const t = await r.text();
      if (!r.ok) return send(res, 502, { error: t.slice(0, 300) });
      return send(res, 200, { text: (JSON.parse(t).text || "").trim() });
    } catch (e) { return send(res, 502, { error: `Spracherkennung nicht erreichbar (${e.cause?.code || e.message})` }); }
  }

  async function tts(req, res) {
    const c = C();
    const p = JSON.parse((await readBody(req)).toString() || "{}");
    const text = String(p.text || "").trim().slice(0, 4000);
    const speed = Math.max(0.5, Math.min(2, Number(p.speed) || 1));
    if (!text) { res.writeHead(204, SEC_HEADERS); return res.end(); }
    try {
      if (c.ttsBackend === "elevenlabs") {
        if (!c.elevenKey) return send(res, 503, { error: "ElevenLabs-Key fehlt (Einstellungen)" });
        const body = { text, model_id: c.elevenModel };
        if (Math.abs(speed - 1) > 0.01) body.voice_settings = { speed: Math.max(0.7, Math.min(1.2, speed)) };
        const r = await fetch(`https://api.elevenlabs.io/v1/text-to-speech/${encodeURIComponent(c.elevenVoice)}?output_format=mp3_44100_128`,
          { method: "POST", headers: { "xi-api-key": c.elevenKey, "Content-Type": "application/json" }, body: JSON.stringify(body), signal: timeout(60000) });
        if (!r.ok) return send(res, r.status === 429 ? 429 : 502, { error: `ElevenLabs ${r.status}: ${(await r.text()).slice(0, 300)}` });
        return send(res, 200, Buffer.from(await r.arrayBuffer()), "audio/mpeg");
      }
      const r = await fetch(`${c.audioUrl}/v1/audio/speech`, { method: "POST", headers: { Authorization: `Bearer ${c.audioKey}`, "Content-Type": "application/json" },
        body: JSON.stringify({ input: text, response_format: "mp3", speed }), signal: timeout(60000) });
      if (!r.ok) return send(res, 502, { error: (await r.text()).slice(0, 300) });
      return send(res, 200, Buffer.from(await r.arrayBuffer()), r.headers.get("content-type") || "audio/mpeg");
    } catch (e) { return send(res, 502, { error: `Stimme nicht erreichbar (${e.cause?.code || e.message})` }); }
  }

  // ------------------------------------------------------------ Status
  async function status() {
    const c = C();
    const out = { name: c.agentName, mode: c.hermesMode, tts: c.ttsBackend === "browser" ? "browser" : c.ttsBackend, stt: c.sttBackend,
      hermes: false, audio: false, model: null, reasoning: c.reasoning || "hermes", desktop: true, notify_mode: c.notifyMode,
      configured: !!(c.hermesUrl && c.hermesKey),
      lagebild: c.dashboardUrl && c.dashboardToken ? "dashboard" : "aus" };
    if (state.error) out.lagebild_error = state.error;
    else if (out.lagebild === "dashboard" && !state.ts) out.lagebild_pending = true;
    if (c.hermesUrl) {
      const t0 = Date.now();
      try {
        const r = await fetch(`${c.hermesUrl}/health`, { signal: timeout(3000) });
        out.hermes = r.ok; out.latency_ms = Date.now() - t0;
        const m = await fetch(`${c.hermesUrl}/v1/models`, { headers: hermesHeaders(c), signal: timeout(3000) });
        if (m.ok) { const d = (await m.json()).data || []; out.model = d[0]?.id || null; }
        else if (m.status === 401) out.hermes_error = "API-Key falsch";
      } catch (e) { out.hermes_error = e.cause?.code || e.message; }
    }
    const needEleven = c.sttBackend === "elevenlabs" || c.ttsBackend === "elevenlabs";
    out.audio = needEleven ? !!c.elevenKey : (c.ttsBackend === "browser" || !!c.audioUrl);
    return out;
  }

  // ------------------------------------------------------------ Aufträge + Log aus dem Hermes-Dashboard
  async function pollDashboard() {
    const c = C();
    if (!c.dashboardUrl || !c.dashboardToken) { state.error = null; return; }
    const hdr = { Authorization: `Bearer ${c.dashboardToken}` };
    try {
      const r = await fetch(`${c.dashboardUrl}/api/plugins/kanban/board`, { headers: hdr, signal: timeout(20000) });
      if (!r.ok) throw new Error(`Kanban HTTP ${r.status}`);
      const tasks = ((await r.json()).columns || []).flatMap((col) => col.tasks || []);
      // Statuswechsel erkennen → der Agent meldet sich (erster Durchlauf merkt sich nur den Stand)
      const now = new Map(tasks.map((t) => [String(t.id), String(t.status)]));
      if (known && c.notifyEnabled) {
        for (const t of tasks) {
          const id = String(t.id), st = String(t.status);
          if (!c.notifyStatuses.has(st) || known.get(id) === st) continue;
          if (c.notifyAssignees.size && !c.notifyAssignees.has(String(t.assignee || ""))) continue;
          let result = t.result || t.latest_summary || "";
          try {
            const d = await fetch(`${c.dashboardUrl}/api/plugins/kanban/tasks/${encodeURIComponent(id)}`, { headers: hdr, signal: timeout(20000) });
            if (d.ok) { const full = (await d.json()).task || {}; result = full.result || full.latest_summary || result; }
          } catch {}
          notes.push({ seq: ++noteSeq, ts: Math.floor(Date.now() / 1000), id, title: String(t.title || "").slice(0, 300),
            assignee: String(t.assignee || "").slice(0, 64), status: st, result: String(result || "").slice(0, 2500) });
          if (notes.length > 100) notes.splice(0, notes.length - 100);
        }
      }
      known = now;
      let logs = [];
      if (c.logName) {
        const lr = await fetch(`${c.dashboardUrl}/api/logs?file=${encodeURIComponent(c.logName)}&lines=${Math.min(500, c.logLines * 2)}`, { headers: hdr, signal: timeout(20000) });
        if (lr.ok) {
          const skip = c.logSkip ? new RegExp(c.logSkip) : null;
          logs = ((await lr.json()).lines || []).map((l) => String(l).replace(/\n$/, "")).filter((l) => l.trim() && !(skip && skip.test(l))).slice(-c.logLines);
        }
      }
      Object.assign(state, { ts: Math.floor(Date.now() / 1000), source: "dashboard", error: null, logs,
        tasks: tasks.filter((t) => !FINISHED.has(t.status)).slice(0, 200)
          .map((t) => Object.fromEntries(TASK_KEYS.map((k) => [k, t[k] == null ? null : String(t[k]).slice(0, 300)]))) });
    } catch (e) {
      state.error = `Dashboard: ${e.cause?.code || e.message}`.slice(0, 200);
    }
  }
  function scheduleDashboard() {
    clearTimeout(dashTimer);
    const loop = async () => { await pollDashboard(); dashTimer = setTimeout(loop, C().dashboardInterval * 1000); };
    loop();
  }

  // ------------------------------------------------------------ Router
  const server = http.createServer(async (req, res) => {
    // Nur Anfragen von diesem Rechner und von der eigenen Oberfläche
    const host = (req.headers.host || "").split(":")[0];
    if (!["127.0.0.1", "localhost"].includes(host)) return send(res, 403, { error: "forbidden" });
    // Nur das eigene App-Fenster kennt den Start-Schlüssel (Cookie) – andere Programme auf dem PC bleiben draußen
    if (hooks.token) {
      const m = /(?:^|;\s*)ct=([a-f0-9]+)/.exec(req.headers.cookie || "");
      const ok = m && m[1].length === hooks.token.length &&
        require("crypto").timingSafeEqual(Buffer.from(m[1]), Buffer.from(hooks.token));
      if (!ok) return send(res, 403, { error: "forbidden" });
    }
    const origin = req.headers.origin;
    if (req.method !== "GET" && origin && !/^http:\/\/(127\.0\.0\.1|localhost):\d+$/.test(origin)) return send(res, 403, { error: "forbidden" });
    const url = new URL(req.url, "http://127.0.0.1");
    try {
      if (req.method === "GET" && (url.pathname === "/" || url.pathname === "/index.html"))
        return send(res, 200, fs.readFileSync(path.join(UI_DIR, "index.html")), "text/html; charset=utf-8");
      if (req.method === "GET" && url.pathname === "/settings")
        return send(res, 200, fs.readFileSync(path.join(UI_DIR, "settings.html")), "text/html; charset=utf-8");
      if (req.method === "GET" && url.pathname === "/icon.svg")
        return send(res, 200, '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 100 100"><rect width="100" height="100" fill="#05080d"/><circle cx="50" cy="50" r="30" fill="none" stroke="#3ee0ff" stroke-width="5"/><circle cx="50" cy="50" r="14" fill="#3ee0ff"/></svg>', "image/svg+xml");
      if (req.method === "GET" && url.pathname === "/manifest.webmanifest") return send(res, 200, { name: C().agentName });
      if (req.method === "GET" && url.pathname === "/health") return send(res, 200, { ok: true });
      if (req.method === "GET" && url.pathname === "/api/status") return send(res, 200, await status());
      if (req.method === "GET" && url.pathname === "/api/config") return send(res, 200, { name: C().agentName, tts: C().ttsBackend, desktop: true, notify_mode: C().notifyMode });
      if (req.method === "GET" && url.pathname === "/api/notifications") {
        const after = Number(url.searchParams.get("after") ?? -1);
        return send(res, 200, after < 0 ? { seq: noteSeq, items: [] }
          : { seq: noteSeq, items: notes.filter((n) => n.seq > after).map(({ claimed, ...n }) => n) });
      }
      if (req.method === "POST" && url.pathname === "/api/notifications/claim") {
        const p = JSON.parse((await readBody(req)).toString() || "{}");
        const n = notes.find((x) => x.seq === Number(p.seq));
        if (!n || n.claimed) return send(res, 200, { ok: false });
        n.claimed = true; return send(res, 200, { ok: true });
      }
      if (req.method === "GET" && url.pathname === "/api/state")
        return send(res, 200, { ...state, age: state.ts ? Math.floor(Date.now() / 1000) - state.ts : null });
      if (req.method === "POST" && url.pathname === "/api/chat") {
        const p = JSON.parse((await readBody(req)).toString() || "{}");
        const text = String(p.text || "").trim();
        if (!text) return send(res, 400, { error: "leer" });
        if (text.length > MAX_TEXT) return send(res, 413, { error: "Nachricht zu lang (max. 64 KB)" });
        return streamChat(res, text, String(p.session || "main").slice(0, 64));
      }
      if (req.method === "POST" && url.pathname === "/api/reset") {
        const p = JSON.parse((await readBody(req)).toString() || "{}"); chatHistory.delete(String(p.session || "main")); return send(res, 200, { ok: true });
      }
      if (req.method === "POST" && url.pathname === "/api/stt") return stt(req, res);
      if (req.method === "POST" && url.pathname === "/api/tts") return tts(req, res);
      if (url.pathname === "/api/settings") {
        if (req.method === "GET") return send(res, 200, hooks.getPublicSettings ? hooks.getPublicSettings() : {});
        if (req.method === "POST") {
          const p = JSON.parse((await readBody(req)).toString() || "{}");
          if (hooks.saveSettings) await hooks.saveSettings(p);
          scheduleDashboard();
          return send(res, 200, { ok: true });
        }
      }
      if (req.method === "POST" && url.pathname === "/api/test") {
        return send(res, 200, await status());
      }
      return send(res, 404, { error: "not found" });
    } catch (e) {
      console.error("[hermesvi]", e);
      if (!res.headersSent) send(res, 500, { error: String(e.message || e) });
    }
  });

  return {
    listen: (port = 0) => new Promise((resolve) => server.listen(port, "127.0.0.1", () => { scheduleDashboard(); resolve(server.address().port); })),
    close: () => { clearTimeout(dashTimer); server.close(); },
    refresh: scheduleDashboard,
  };
}

module.exports = { createServer, DEFAULT_HINT };

// Direkt starten (zum Testen ohne Electron): node server.js  → liest config.json im selben Ordner
if (require.main === module) {
  const cfgPath = process.env.HERMESVI_CONFIG || path.join(__dirname, "config.json");
  const load = () => { try { return JSON.parse(fs.readFileSync(cfgPath, "utf8")); } catch { return {}; } };
  createServer(load).listen(Number(process.env.PORT) || 8810).then((p) => console.log(`HermesVI Desktop-Server: http://127.0.0.1:${p}`));
}
