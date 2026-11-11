/* Propelo service worker: makes the app installable and shows a friendly page when you're offline.
   It never caches your data: API calls always go to the network. */
const CACHE = "careeros-shell-v1";
const SHELL = ["/offline", "/icons/icon-192.png"];
self.addEventListener("install", (e) => {
  e.waitUntil(caches.open(CACHE).then((c) => c.addAll(SHELL)).then(() => self.skipWaiting()));
});
self.addEventListener("activate", (e) => {
  e.waitUntil(caches.keys().then((keys) => Promise.all(keys.filter((k) => k !== CACHE).map((k) => caches.delete(k)))).then(() => self.clients.claim()));
});
self.addEventListener("fetch", (e) => {
  const req = e.request;
  if (req.method !== "GET" || new URL(req.url).origin !== self.location.origin) return;
  if (req.mode === "navigate") {
    e.respondWith(fetch(req).catch(() => caches.match("/offline")));
    return;
  }
  if (new URL(req.url).pathname.startsWith("/icons/")) {
    e.respondWith(caches.match(req).then((hit) => hit || fetch(req)));
  }
});
