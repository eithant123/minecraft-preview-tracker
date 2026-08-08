const CACHE_NAME = "waitradar-v2";
const STATIC_ASSETS = [
  "./index.html",
  "./settings.html",
  "./manifest.json",
  "./icon-192.png",
  "./icon-512.png"
];

self.addEventListener("install", (event) => {
  event.waitUntil(
    caches.open(CACHE_NAME).then((cache) => cache.addAll(STATIC_ASSETS))
  );
  self.skipWaiting();
});

self.addEventListener("activate", (event) => {
  event.waitUntil(
    caches.keys().then((names) =>
      Promise.all(
        names.filter((n) => n !== CACHE_NAME).map((n) => caches.delete(n))
      )
    )
  );
  self.clients.claim();
});

self.addEventListener("fetch", (event) => {
  const url = new URL(event.request.url);

  // status.json y las páginas HTML: siempre intenta traer lo más nuevo de
  // la red primero. Si no hay internet, ahí sí cae a la última copia guardada.
  const isHTML = url.pathname.endsWith(".html") || url.pathname.endsWith("/");
  if (url.pathname.endsWith("status.json") || isHTML) {
    event.respondWith(
      fetch(event.request)
        .then((res) => {
          const copy = res.clone();
          caches.open(CACHE_NAME).then((cache) => cache.put(event.request, copy));
          return res;
        })
        .catch(() => caches.match(event.request))
    );
    return;
  }

  // Íconos y manifest: caché primero, red como respaldo (no cambian seguido).
  event.respondWith(
    caches.match(event.request).then((cached) => cached || fetch(event.request))
  );
});
