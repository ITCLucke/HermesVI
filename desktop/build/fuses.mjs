// Electron-Fuses für die Windows-App setzen (electron-packager kennt sie nicht; die Linux-App setzt
// electron-builder über "electronFuses" in package.json). Aufruf: node build/fuses.mjs dist/HermesVI-win32-x64/HermesVI.exe
import { flipFuses, FuseVersion, FuseV1Options } from "@electron/fuses";

const exe = process.argv[2];
if (!exe) { console.error("Pfad zur HermesVI.exe fehlt"); process.exit(1); }
await flipFuses(exe, {
  version: FuseVersion.V1,
  [FuseV1Options.RunAsNode]: false,                              // HermesVI.exe nicht als beliebiges Node.js missbrauchbar
  [FuseV1Options.EnableNodeOptionsEnvironmentVariable]: false,   // kein Code über NODE_OPTIONS einschleusbar
  [FuseV1Options.EnableNodeCliInspectArguments]: false,          // kein Debugger über --inspect
  [FuseV1Options.OnlyLoadAppFromAsar]: true,                     // App-Code nur aus app.asar
  [FuseV1Options.GrantFileProtocolExtraPrivileges]: false,       // file:// ohne Sonderrechte (wird nicht genutzt)
});
console.log("Fuses gesetzt:", exe);
