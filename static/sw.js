const CACHE_NAME = 'signbridge-cache-v1';
const ASSETS_TO_CACHE = [
  '/',
  '/style.css?v=1.9',
  '/css/cwasa.css',
  '/js/allcsa.js',
  '/js/script.js',
  '/js/sigmlFiles.json',
  '/manifest.json'
];

// Install Service Worker
self.addEventListener('install', event => {
  event.waitUntil(
    caches.open(CACHE_NAME)
      .then(cache => {
        console.log('[Service Worker] Caching App Shell');
        return cache.addAll(ASSETS_TO_CACHE);
      })
      .then(() => self.skipWaiting())
  );
});

// Activate Service Worker
self.addEventListener('activate', event => {
  event.waitUntil(
    caches.keys().then(cacheNames => {
      return Promise.all(
        cacheNames.map(cache => {
          if (cache !== CACHE_NAME) {
            console.log('[Service Worker] Clearing Old Cache');
            return caches.delete(cache);
          }
        })
      );
    }).then(() => self.clients.claim())
  );
});

// Fetch Intercept for Offline Support
self.addEventListener('fetch', event => {
  // Let the browser handle external requests / APIs unless offline
  event.respondWith(
    caches.match(event.request)
      .then(response => {
        if (response) {
          return response; // Return from cache
        }
        
        return fetch(event.request).then(fetchResponse => {
          // Cache dynamic files if they are local assets, SigML files, or CDN libraries
          if (event.request.url.includes('/static/') || event.request.url.includes('/SignFiles/') || event.request.url.includes('cdn.jsdelivr.net')) {
            return caches.open(CACHE_NAME).then(cache => {
              cache.put(event.request, fetchResponse.clone());
              return fetchResponse;
            });
          }
          return fetchResponse;
        }).catch(err => {
          // Catch offline fallback for APIs or missing assets
          console.warn('[Service Worker] Fetch failed; returning offline placeholder if applicable', err);
        });
      })
  );
});
