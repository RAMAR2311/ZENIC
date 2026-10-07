/* ==========================================================================
   Service Worker — Zenic Master Control PWA
   Estrategia: Network First con fallback a Cache y soporte Offline
   ========================================================================== */

const CACHE_NAME = 'zenic-crm-v1';

// Recursos críticos para cachear inicialmente
const STATIC_ASSETS = [
  '/',
  '/static/manifest.json',
  '/static/img/LOGO%20ZENIC.png',
  '/static/img/icons/icon-192x192.png',
  '/static/img/icons/icon-512x512.png',
  'https://cdn.jsdelivr.net/npm/bootstrap@5.3.2/dist/css/bootstrap.min.css',
  'https://cdn.jsdelivr.net/npm/bootstrap@5.3.2/dist/js/bootstrap.bundle.min.js',
  'https://cdnjs.cloudflare.com/ajax/libs/font-awesome/6.5.1/css/all.min.css',
  'https://cdn.jsdelivr.net/npm/chart.js'
];

// Instalación del Service Worker
self.addEventListener('install', (event) => {
  event.waitUntil(
    caches.open(CACHE_NAME).then((cache) => {
      return cache.addAll(STATIC_ASSETS).catch((err) => {
        console.warn('[SW] Algunos recursos iniciales no pudieron ser cacheados:', err);
      });
    }).then(() => self.skipWaiting())
  );
});

// Activación y limpieza de caches antiguos
self.addEventListener('activate', (event) => {
  event.waitUntil(
    caches.keys().then((cacheNames) => {
      return Promise.all(
        cacheNames.map((cache) => {
          if (cache !== CACHE_NAME) {
            return caches.delete(cache);
          }
        })
      );
    }).then(() => self.clients.claim())
  );
});

// Intercepción de peticiones (Network First con Cache Fallback)
self.addEventListener('fetch', (event) => {
  // Solo procesar peticiones GET (evitar POST de login, formularios, etc.)
  if (event.request.method !== 'GET') {
    return;
  }

  // Ignorar peticiones internas de sockets o extensiones
  const url = new URL(event.request.url);
  if (url.protocol !== 'http:' && url.protocol !== 'https:') {
    return;
  }

  event.respondWith(
    fetch(event.request)
      .then((networkResponse) => {
        // Si la respuesta es válida, clonamos y guardamos en caché
        if (networkResponse && networkResponse.status === 200) {
          const responseToCache = networkResponse.clone();
          caches.open(CACHE_NAME).then((cache) => {
            cache.put(event.request, responseToCache);
          });
        }
        return networkResponse;
      })
      .catch(async () => {
        // En caso de estar sin internet (Offline), responder con caché
        const cachedResponse = await caches.match(event.request);
        if (cachedResponse) {
          return cachedResponse;
        }

        // Si es una petición de navegación HTML y no está en caché, fallback a la raíz
        if (event.request.mode === 'navigate') {
          const fallback = await caches.match('/');
          if (fallback) return fallback;
        }

        return new Response('Sin conexión a Internet. Por favor verifica tu red.', {
          status: 503,
          headers: { 'Content-Type': 'text/plain; charset=utf-8' }
        });
      })
  );
});
