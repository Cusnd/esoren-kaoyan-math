const BUILD_ID = __BUILD_ID__;
const BASE_PATH = __BASE_PATH__;
const CACHE_NAME = `math1-reader-${BUILD_ID}`;
const PRECACHE = __PRECACHE__;
const LEGACY_ROUTES = __LEGACY_ROUTES__;
const OFFLINE_URL = `${BASE_PATH}/offline.html`;

self.addEventListener('install', (event) => {
  event.waitUntil((async () => {
    try {
      const cache = await caches.open(CACHE_NAME);
      await cache.addAll(PRECACHE);
    } catch (error) {
      await caches.delete(CACHE_NAME);
      throw error;
    }
  })());
});

self.addEventListener('activate', (event) => {
  event.waitUntil((async () => {
    const names = await caches.keys();
    await Promise.all(names
      .filter((name) => name.startsWith('math1-reader-') && name !== CACHE_NAME)
      .map((name) => caches.delete(name)));
    await self.clients.claim();
  })());
});

self.addEventListener('message', (event) => {
  if (event.data?.type === 'SKIP_WAITING') self.skipWaiting();
});

function canonicalUrl(request) {
  const url = new URL(request.url);
  const mapped = LEGACY_ROUTES[url.pathname];
  if (!mapped) return null;
  url.pathname = mapped;
  return url.href;
}

function wantsHtml(request) {
  return request.mode === 'navigate' || request.headers.get('accept')?.includes('text/html');
}

self.addEventListener('fetch', (event) => {
  const original = event.request;
  if (original.method !== 'GET') return;
  const url = new URL(original.url);
  if (url.origin !== self.location.origin) return;
  if (url.pathname !== BASE_PATH && !url.pathname.startsWith(`${BASE_PATH}/`)) return;
  const mappedUrl = canonicalUrl(original);
  const cacheKey = mappedUrl ?? original;
  event.respondWith((async () => {
    const cached = await caches.match(cacheKey, { ignoreSearch: true });
    if (cached) return cached;
    try {
      const response = await fetch(cacheKey);
      if (!response.ok && wantsHtml(original)) {
        const fallback = await caches.match(OFFLINE_URL);
        if (fallback) return fallback;
      }
      if (response.ok) {
        const cache = await caches.open(CACHE_NAME);
        await cache.put(cacheKey, response.clone());
      }
      return response;
    } catch (error) {
      if (wantsHtml(original)) return (await caches.match(OFFLINE_URL)) ?? Response.error();
      throw error;
    }
  })());
});
