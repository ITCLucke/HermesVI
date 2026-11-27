// Kopiert die gemeinsame Oberfläche (ui/) in die beiden Varianten.
// ui/ ist die einzige Quelle – docker/static/ und desktop/ui/ werden daraus erzeugt (nicht im Git).
//   node scripts/sync-ui.mjs          → kopieren
//   node scripts/sync-ui.mjs --check  → nur prüfen, ob die Kopien aktuell sind (Exit-Code 1, wenn nicht)
import { cpSync, mkdirSync, readFileSync, rmSync, existsSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";

const root = join(dirname(fileURLToPath(import.meta.url)), "..");
const ui = join(root, "ui");
const targets = {
  "docker/static": ["index.html", "login.html", "icons"],      // Web-App: mit Login-Seite, ohne Desktop-Einstellungen
  "desktop/ui":    ["index.html", "settings.html", "icons"],   // Desktop-App: Einstellungsseite, kein Login (Token pro Start)
};
const check = process.argv.includes("--check");
let stale = 0;

const same = (a, b) => existsSync(b) && readFileSync(a).equals(readFileSync(b));
for (const [dir, files] of Object.entries(targets)) {
  const dest = join(root, dir);
  for (const f of files) {
    const src = join(ui, f), dst = join(dest, f);
    if (check) {
      const list = f === "icons" ? ["apple-touch-icon.png", "icon-192.png", "icon-512.png"].map((x) => join("icons", x)) : [f];
      for (const x of list) if (!same(join(ui, x), join(dest, x))) { console.error(`veraltet: ${dir}/${x}`); stale++; }
      continue;
    }
    mkdirSync(dirname(dst), { recursive: true });
    rmSync(dst, { recursive: true, force: true });
    cpSync(src, dst, { recursive: true });
  }
}
if (check && stale) { console.error("→ node scripts/sync-ui.mjs ausführen"); process.exit(1); }
if (!check) console.log("Oberfläche kopiert: " + Object.keys(targets).join(", "));
