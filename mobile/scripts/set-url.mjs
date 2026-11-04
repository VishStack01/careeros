// Point the app at your CareerOS server: CAREEROS_APP_URL=https://your-domain npm run set-url
// The address must be https. It is written into capacitor.config.json (server.url).
import { readFileSync, writeFileSync } from "node:fs";

const url = (process.env.CAREEROS_APP_URL || "").trim().replace(/\/+$/, "");
const path = new URL("../capacitor.config.json", import.meta.url);
const config = JSON.parse(readFileSync(path, "utf8"));
if (!url) {
  console.log(`Using ${config.server.url}. Set CAREEROS_APP_URL to change it.`);
  process.exit(0);
}
if (!/^https:\/\/[a-z0-9.-]+(:\d+)?$/i.test(url)) {
  console.error("CAREEROS_APP_URL must be an https:// address with no path, e.g. https://app.example.com");
  process.exit(1);
}
config.server.url = url;
writeFileSync(path, JSON.stringify(config, null, 2) + "\n");
const offline = new URL("../www/offline.html", import.meta.url);
writeFileSync(offline, readFileSync(offline, "utf8").replace(/data-app-url="[^"]*"/, `data-app-url="${url}"`));
console.log(`CareerOS app now opens ${url}`);
