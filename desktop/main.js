// HermesVI Desktop – Electron-Hauptprozess
"use strict";
const { app, BrowserWindow, Tray, Menu, globalShortcut, nativeImage, safeStorage, session, shell, Notification } = require("electron");
const fs = require("fs");
const path = require("path");
const crypto = require("crypto");
const os = require("os");
const { createServer } = require("./server");
const TOKEN = crypto.randomBytes(32).toString("hex");   // pro Start neu, nur dem eigenen Fenster bekannt
const IS_LINUX = process.platform === "linux";

app.setAppUserModelId("io.github.hermesvi");
app.commandLine.appendSwitch("autoplay-policy", "no-user-gesture-required");

if (!app.requestSingleInstanceLock()) { app.quit(); }
const wantsToggleMic = (argv) => argv.includes("--toggle-mic");

const SECRET_KEYS = ["hermesKey", "elevenKey", "dashboardToken", "audioKey"];
const PUBLIC_KEYS = ["agentName", "userName", "hermesUrl", "hermesMode", "conversation", "reasoning", "voiceHint",
  "sttBackend", "ttsBackend", "sttLanguage", "elevenVoice", "elevenModel", "elevenSttModel", "audioUrl",
  "dashboardUrl", "dashboardInterval", "logName", "logLines", "hotkey", "startHidden",
  "notifyEnabled", "notifyStatuses", "notifyAssignees", "notifyMode", "attachEnabled"];
const URL_KEYS = ["hermesUrl", "audioUrl", "dashboardUrl"];

let cfgPath, config = {}, win = null, tray = null, server = null, port = 0, quitting = false;

// ------------------------------------------------------------ Einstellungen (Keys verschlüsselt per Windows DPAPI)
function enc(v) { return safeStorage.isEncryptionAvailable() ? "enc:" + safeStorage.encryptString(v).toString("base64") : "b64:" + Buffer.from(v).toString("base64"); }
function dec(v) {
  if (!v) return "";
  try {
    if (v.startsWith("enc:")) return safeStorage.decryptString(Buffer.from(v.slice(4), "base64"));
    if (v.startsWith("b64:")) return Buffer.from(v.slice(4), "base64").toString();
  } catch { return ""; }
  return v;
}
function loadConfig() {
  try { const raw = JSON.parse(fs.readFileSync(cfgPath, "utf8"));
    config = { ...raw, secrets: Object.fromEntries(SECRET_KEYS.map((k) => [k, dec(raw.secrets?.[k])])) };
  } catch { config = { secrets: {} }; }
}
function saveConfig() {
  const out = { ...config, secrets: Object.fromEntries(SECRET_KEYS.map((k) => [k, config.secrets?.[k] ? enc(config.secrets[k]) : ""])) };
  fs.mkdirSync(path.dirname(cfgPath), { recursive: true, mode: 0o700 });
  fs.writeFileSync(cfgPath, JSON.stringify(out, null, 2), { mode: 0o600 });
  try { fs.chmodSync(cfgPath, 0o600); } catch {}   // auch bei schon vorhandener Datei: nur der eigene Benutzer darf lesen
}
// Einstellungen aus Vorabversionen (anderer App-Name) einmalig übernehmen
function migrateOldConfig() {
  if (fs.existsSync(cfgPath)) return;
  for (const old of ["Charlie", "charlie-desktop"]) {
    const p = path.join(app.getPath("appData"), old, "config.json");
    if (fs.existsSync(p)) { try { fs.mkdirSync(path.dirname(cfgPath), { recursive: true }); fs.copyFileSync(p, cfgPath); } catch {} return; }
  }
}
// Autostart: Windows über die Registry (Electron), Linux über ~/.config/autostart
const AUTOSTART_FILE = path.join(os.homedir(), ".config", "autostart", "hermesvi.desktop");
function getAutostart() {
  if (IS_LINUX) return fs.existsSync(AUTOSTART_FILE);
  return app.getLoginItemSettings().openAtLogin;
}
function setAutostart(on) {
  if (!IS_LINUX) return app.setLoginItemSettings({ openAtLogin: on, args: ["--hidden"] });
  try {
    if (!on) { fs.rmSync(AUTOSTART_FILE, { force: true }); return; }
    const exe = process.env.APPIMAGE || process.execPath;
    fs.mkdirSync(path.dirname(AUTOSTART_FILE), { recursive: true });
    fs.writeFileSync(AUTOSTART_FILE, `[Desktop Entry]\nType=Application\nName=HermesVI\nExec="${exe}" --hidden\nIcon=hermesvi\nX-GNOME-Autostart-enabled=true\n`);
  } catch (e) { console.error("Autostart:", e); }
}
const publicSettings = () => ({
  ...Object.fromEntries(PUBLIC_KEYS.map((k) => [k, config[k] ?? null])),
  secretsSet: Object.fromEntries(SECRET_KEYS.map((k) => [k, !!config.secrets?.[k]])),
  autostart: getAutostart(),
  encrypted: strongEncryption(),
  platform: process.platform,
  hotkeyDefault: "CommandOrControl+Shift+Space",
});
// Unter Linux ohne Schlüsselbund nutzt Electron nur eine Ersatz-Kodierung („basic_text“) – das ist keine echte Verschlüsselung
function strongEncryption() {
  if (!safeStorage.isEncryptionAvailable()) return false;
  if (IS_LINUX && typeof safeStorage.getSelectedStorageBackend === "function") {
    const b = safeStorage.getSelectedStorageBackend();
    if (b === "basic_text" || b === "unknown") return false;
  }
  return true;
}
// Nur erwartete Typen und gültige Adressen übernehmen
function cleanValue(k, v) {
  if (v === null || typeof v === "boolean" || typeof v === "number") return Number.isFinite(v) || typeof v !== "number" ? v : null;
  if (typeof v !== "string") return undefined;
  v = v.trim().slice(0, k === "voiceHint" ? 2000 : 500);
  if (URL_KEYS.includes(k) && v) {
    try { const u = new URL(v); if (!["http:", "https:"].includes(u.protocol)) return undefined; } catch { return undefined; }
  }
  return v;
}
async function saveSettings(p) {
  if (!p || typeof p !== "object") return;
  for (const k of PUBLIC_KEYS) if (k in p) { const v = cleanValue(k, p[k]); if (v !== undefined) config[k] = v; }
  config.secrets = config.secrets || {};
  for (const k of SECRET_KEYS) if (typeof p[k] === "string" && p[k].trim() !== "") config.secrets[k] = p[k].trim().slice(0, 500);
  for (const k of SECRET_KEYS) if (p["clear_" + k]) config.secrets[k] = "";
  if (typeof p.autostart === "boolean") setAutostart(p.autostart);
  saveConfig();
  registerHotkey();
  if (tray) tray.setToolTip(config.agentName || "Hermes");
}

// ------------------------------------------------------------ Fenster
function icon(size) {
  const p = path.join(__dirname, "assets", size >= 64 ? "icon.png" : "tray.png");
  return nativeImage.createFromPath(p);
}
function createWindow(show = true) {
  win = new BrowserWindow({
    width: 1500, height: 920, minWidth: 420, minHeight: 600, show: false, backgroundColor: "#05080d",
    title: config.agentName || "Hermes", icon: icon(256), autoHideMenuBar: true,
    webPreferences: { contextIsolation: true, nodeIntegration: false, sandbox: true, backgroundThrottling: false },
  });
  win.removeMenu();
  const configured = config.hermesUrl && config.secrets?.hermesKey;
  win.loadURL(`http://127.0.0.1:${port}/${configured ? "" : "settings"}`);
  win.once("ready-to-show", () => { if (show) win.show(); });
  win.on("close", (e) => { if (!quitting) { e.preventDefault(); win.hide(); } });
  win.webContents.setWindowOpenHandler(({ url }) => { if (/^https?:/.test(url)) shell.openExternal(url); return { action: "deny" }; });
  // Das Fenster darf nur die eigene Oberfläche zeigen – nie eine fremde Seite
  win.webContents.on("will-navigate", (e, url) => {
    if (!url.startsWith(`http://127.0.0.1:${port}/`)) { e.preventDefault(); if (/^https?:/.test(url)) shell.openExternal(url); }
  });
}
function showWindow() { if (!win) createWindow(); win.show(); if (win.isMinimized()) win.restore(); win.focus(); }

// ------------------------------------------------------------ Tastenkürzel + Infobereich
function toggleMic() {
  showWindow();
  win.webContents.executeJavaScript("document.getElementById('chatMic') && document.getElementById('chatMic').click()").catch(() => {});
}
function registerHotkey() {
  globalShortcut.unregisterAll();
  const key = config.hotkey || "CommandOrControl+Shift+Space";
  try {
    // Unter GNOME/Wayland sind globale Kürzel für Apps gesperrt → dort ein System-Kürzel auf „hermesvi --toggle-mic“ legen
    globalShortcut.register(key, toggleMic);
  } catch { /* ungültiges Kürzel */ }
}
function createTray() {
  tray = new Tray(icon(16));
  tray.setToolTip(config.agentName || "Hermes");
  const menu = () => Menu.buildFromTemplate([
    { label: `${config.agentName || "Hermes"} öffnen`, click: showWindow },
    { label: "Einstellungen …", click: () => { showWindow(); win.loadURL(`http://127.0.0.1:${port}/settings`); } },
    { type: "separator" },
    { label: IS_LINUX ? "Beim Anmelden starten" : "Mit Windows starten", type: "checkbox", checked: getAutostart(),
      click: (it) => setAutostart(it.checked) },
    { type: "separator" },
    { label: "Beenden", click: () => { quitting = true; app.quit(); } },
  ]);
  tray.setContextMenu(menu());
  tray.on("click", () => (win && win.isVisible() ? win.hide() : showWindow()));
  tray.on("right-click", () => tray.setContextMenu(menu()));
}

// ------------------------------------------------------------ Start
app.on("second-instance", (_e, argv) => { if (wantsToggleMic(argv)) toggleMic(); else showWindow(); });
app.whenReady().then(async () => {
  cfgPath = path.join(app.getPath("userData"), "config.json");
  migrateOldConfig();
  loadConfig();
  if (fs.existsSync(cfgPath)) { try { fs.chmodSync(cfgPath, 0o600); } catch {} }
  // Mikrofon nur für die eigene Oberfläche erlauben
  session.defaultSession.setPermissionRequestHandler((wc, perm, cb, details) => {
    const ok = (perm === "media" || perm === "audioCapture" || perm === "notifications") && /^http:\/\/127\.0\.0\.1:\d+\//.test(details.requestingUrl || wc.getURL());
    cb(ok);
  });
  session.defaultSession.setPermissionCheckHandler((wc, perm, origin) => (perm === "media" || perm === "notifications") && /^http:\/\/127\.0\.0\.1:\d+$/.test(origin));
  server = createServer(() => config, { getPublicSettings: publicSettings, saveSettings, token: TOKEN });
  port = await server.listen(0);
  await session.defaultSession.cookies.set({ url: `http://127.0.0.1:${port}`, name: "ct", value: TOKEN, httpOnly: true, sameSite: "strict" });
  const hidden = process.argv.includes("--hidden") || config.startHidden;
  createWindow(!hidden);
  createTray();
  registerHotkey();
  if (hidden && Notification.isSupported())
    new Notification({ title: config.agentName || "Hermes", body: "Läuft im Infobereich. Strg+Umschalt+Leertaste zum Sprechen." }).show();
  if (wantsToggleMic(process.argv)) setTimeout(toggleMic, 1500);
});
app.on("window-all-closed", (e) => e.preventDefault());
app.on("before-quit", () => { quitting = true; globalShortcut.unregisterAll(); server && server.close(); });
