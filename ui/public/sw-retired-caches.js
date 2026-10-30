// Loaded into the app's service worker by `workbox.importScripts` (vite.config.ts).
//
// Workers before this one kept every /api/ GET in a cache named "api-cache", keyed
// by URL alone, so a response read while signed in stayed on the device after
// sign-out. The worker no longer caches the API, and Workbox only clears its own
// precaches, so the cache an older worker left behind is deleted here, once the
// new worker activates and nothing can write to it again.
self.addEventListener("activate", (event) => {
	event.waitUntil(caches.delete("api-cache"));
});
