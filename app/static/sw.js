// Service-Worker für das Z-B Agilityportal.
// Cached die App-Shell + statische Assets (network-first für Seiten/Daten).
// Achtung: Das Portal ist nicht offline-fähig — der Server muss erreichbar sein;
// der Cache dient nur als Fallback bei kurzen Verbindungsabbrüchen.

const CACHE_NAME = "agilityportal-v1";
const APP_SHELL = [
  "/static/icon.svg",
  "/static/manifest.json",
  "https://cdn.jsdelivr.net/npm/bootstrap@5.3.3/dist/css/bootstrap.min.css",
  "https://cdn.jsdelivr.net/npm/bootstrap@5.3.3/dist/js/bootstrap.bundle.min.js",
];

self.addEventListener("install", (event) => {
  event.waitUntil(
    caches.open(CACHE_NAME).then((cache) => cache.addAll(APP_SHELL))
  );
  self.skipWaiting();
});

self.addEventListener("activate", (event) => {
  event.waitUntil(
    caches.keys().then((keys) =>
      Promise.all(keys.filter((k) => k !== CACHE_NAME).map((k) => caches.delete(k)))
    )
  );
  self.clients.claim();
});

self.addEventListener("fetch", (event) => {
  const url = new URL(event.request.url);

  // Nur GET cachen
  if (event.request.method !== "GET") return;

  // Statisches: cache-first
  if (url.pathname.startsWith("/static/") || url.hostname === "cdn.jsdelivr.net") {
    event.respondWith(
      caches.match(event.request).then((hit) => hit || fetch(event.request))
    );
    return;
  }

  // Seiten/Daten: network-first, Fallback auf Cache (z.B. kurzer WLAN-Aussetzer)
  event.respondWith(
    fetch(event.request)
      .then((response) => {
        if (response && response.ok && response.type === "basic") {
          const copy = response.clone();
          caches.open(CACHE_NAME).then((cache) => cache.put(event.request, copy));
        }
        return response;
      })
      .catch(() => caches.match(event.request))
  );
});
