// HermesVI Desktop – Einstellungen prüfen und übernehmen (ohne Electron, damit es testbar ist)
"use strict";

const SECRET_KEYS = ["hermesKey", "elevenKey", "dashboardToken", "audioKey"];
const PUBLIC_KEYS = ["agentName", "userName", "hermesUrl", "hermesMode", "conversation", "reasoning", "voiceHint",
  "sttBackend", "ttsBackend", "sttLanguage", "elevenVoice", "elevenModel", "elevenSttModel", "audioUrl",
  "dashboardUrl", "dashboardInterval", "logName", "logLines", "hotkey", "startHidden",
  "notifyEnabled", "notifyStatuses", "notifyAssignees", "notifyMode", "attachEnabled"];
const URL_KEYS = ["hermesUrl", "audioUrl", "dashboardUrl"];
// Jeder Schlüssel gehört zu genau einer Adresse: Ändert sich die Adresse, muss der Schlüssel neu eingegeben werden.
// Sonst ginge ein gespeicherter Key nach einer Änderung (versehentlich oder untergeschoben) an einen fremden Server.
const URL_SECRET = { hermesUrl: "hermesKey", audioUrl: "audioKey", dashboardUrl: "dashboardToken" };

// Nur erwartete Typen und gültige Adressen übernehmen
function cleanValue(k, v) {
  if (v === null || typeof v === "boolean" || typeof v === "number") return Number.isFinite(v) || typeof v !== "number" ? v : null;
  if (typeof v !== "string") return undefined;
  v = v.trim().slice(0, k === "voiceHint" ? 2000 : 500);
  if (URL_KEYS.includes(k) && v) {
    try { const u = new URL(v); if (!["http:", "https:"].includes(u.protocol)) return undefined; } catch { return undefined; }
    v = v.replace(/\/+$/, "");
  }
  if (k === "elevenVoice" && v && !/^[A-Za-z0-9]{1,64}$/.test(v)) return undefined;
  return v;
}

/** Übernimmt die Eingaben aus der Einstellungsseite in config (verändert config).
 *  Rückgabe: { cleared: [Schlüssel, die wegen einer geänderten Adresse gelöscht wurden] } */
function applySettings(config, p) {
  const cleared = [];
  if (!p || typeof p !== "object") return { cleared };
  config.secrets = config.secrets || {};
  const norm = (u) => String(u || "").replace(/\/+$/, "");
  const oldUrls = Object.fromEntries(URL_KEYS.map((k) => [k, norm(config[k])]));
  for (const k of PUBLIC_KEYS) if (k in p) { const v = cleanValue(k, p[k]); if (v !== undefined) config[k] = v; }
  for (const k of SECRET_KEYS) if (typeof p[k] === "string" && p[k].trim() !== "") config.secrets[k] = p[k].trim().slice(0, 500);
  for (const k of SECRET_KEYS) if (p["clear_" + k]) config.secrets[k] = "";
  for (const [urlKey, secretKey] of Object.entries(URL_SECRET)) {
    const changed = oldUrls[urlKey] && norm(config[urlKey]) !== oldUrls[urlKey];
    const newSecret = typeof p[secretKey] === "string" && p[secretKey].trim() !== "";
    if (changed && !newSecret && config.secrets[secretKey]) { config.secrets[secretKey] = ""; cleared.push(secretKey); }
  }
  return { cleared };
}

module.exports = { SECRET_KEYS, PUBLIC_KEYS, URL_KEYS, URL_SECRET, cleanValue, applySettings };
