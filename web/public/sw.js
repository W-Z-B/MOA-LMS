/* GSA LMS service worker.
 * Caches the application shell (HTML, scripts, styles, icons) so the app opens without a connection.
 * API responses go straight to the network and are never cached here. Requests are queued for retry by the
 * page (offlineQueue.ts), not here.
 *
 * Reading offline (item 4.03): a module the person chose to keep is in a cache of their own,
 * "gsa-lms-offline-<account id>", filled by the page (features/media/offlineStore.ts). When the network
 * cannot be reached, a request for one of those addresses is answered from that cache, and only while its
 * owner is the one signed in on this device (shared phones, ADR 0011): the page names the owner, and it is
 * kept in a small cache of its own so the worker remembers it after it is stopped. The owner's cache is
 * removed when they sign out.
 *
 * Push notices (item 4.04): a notice carries only a title and the page it leads to; tapping it opens that
 * page in the app.
 */
const VERSION = "gsa-lms-shell-v3";
const OFFLINE_PREFIX = "gsa-lms-offline-";
const OWNER_CACHE = "gsa-lms-owner";
const OWNER_KEY = "/__owner";
// The crest and the self-hosted font are part of the frame (item 2.07), so it looks the same offline.
const SHELL = [
  "/",
  "/index.html",
  "/manifest.webmanifest",
  "/favicon.svg",
  "/icon-maskable.svg",
  "/crest.png",
  "/fonts/public-sans-latin-wght.woff2",
];

self.addEventListener("install", (event) => {
  event.waitUntil(caches.open(VERSION).then((cache) => cache.addAll(SHELL)).then(() => self.skipWaiting()));
});

self.addEventListener("activate", (event) => {
  // Old shells go; kept modules and the owner stay.
  const keep = (k) => k === VERSION || k === OWNER_CACHE || k.startsWith(OFFLINE_PREFIX);
  event.waitUntil(
    caches
      .keys()
      .then((keys) => Promise.all(keys.filter((k) => !keep(k)).map((k) => caches.delete(k))))
      .then(() => self.clients.claim()),
  );
});

/** The account signed in on this device, as the page last said; null when nobody is. */
async function owner() {
  const cache = await caches.open(OWNER_CACHE);
  const answer = await cache.match(OWNER_KEY);
  if (!answer) return null;
  const id = Number(await answer.text());
  return Number.isInteger(id) && id > 0 ? id : null;
}

/** An address as it is kept: the page fetches with offline=1, and reads without it. */
function keptAddress(url) {
  const copy = new URL(url);
  copy.searchParams.delete("offline");
  return copy.pathname + copy.search;
}

/** Part of a kept file, for a player that seeks (Range: bytes=start-end). */
async function ranged(response, range) {
  const match = /^bytes=(\d*)-(\d*)$/.exec(range || "");
  if (!match || (!match[1] && !match[2])) return response;
  const body = new Uint8Array(await response.arrayBuffer());
  const size = body.length;
  const start = match[1] ? Number(match[1]) : Math.max(size - Number(match[2]), 0);
  const end = match[1] && match[2] ? Math.min(Number(match[2]), size - 1) : size - 1;
  if (start >= size || start > end) return new Response(null, { status: 416, headers: { "Content-Range": `bytes */${size}` } });
  return new Response(body.slice(start, end + 1), {
    status: 206,
    headers: {
      "Content-Type": response.headers.get("Content-Type") || "application/octet-stream",
      "Content-Range": `bytes ${start}-${end}/${size}`,
      "Content-Length": String(end - start + 1),
      "Accept-Ranges": "bytes",
    },
  });
}

/** The network, or, when it cannot be reached, the signed-in person's kept copy. */
async function networkThenKept(request) {
  try {
    return await fetch(request);
  } catch (error) {
    const id = await owner();
    if (id === null) throw error;
    const cache = await caches.open(`${OFFLINE_PREFIX}${id}`);
    const kept = await cache.match(keptAddress(request.url));
    if (!kept) throw error;
    return ranged(kept, request.headers.get("Range"));
  }
}

self.addEventListener("fetch", (event) => {
  const { request } = event;
  const url = new URL(request.url);
  if (request.method !== "GET" || url.origin !== self.location.origin) return;
  if (url.pathname.startsWith("/admin/")) return; // network only
  if (url.pathname.startsWith("/api/")) {
    event.respondWith(networkThenKept(request));
    return;
  }

  if (request.mode === "navigate") {
    // Network first so deployments land immediately; cached shell when offline.
    event.respondWith(
      fetch(request)
        .then((response) => {
          const copy = response.clone();
          caches.open(VERSION).then((cache) => cache.put("/index.html", copy));
          return response;
        })
        .catch(() => caches.match("/index.html")),
    );
    return;
  }

  // Hashed build assets and icons: cache first, then network, and remember what we fetched.
  event.respondWith(
    caches.match(request).then(
      (cached) =>
        cached ||
        fetch(request).then((response) => {
          if (response.ok) {
            const copy = response.clone();
            caches.open(VERSION).then((cache) => cache.put(request, copy));
          }
          return response;
        }),
    ),
  );
});

// --- push notices (item 4.04) ---

self.addEventListener("push", (event) => {
  let notice = { title: "GSA LMS", link: "/", tag: undefined };
  try {
    notice = { ...notice, ...(event.data ? event.data.json() : {}) };
  } catch {
    /* a notice that is not ours to read still says something arrived */
  }
  event.waitUntil(
    self.registration.showNotification(notice.title, {
      icon: "/crest.png",
      badge: "/crest.png",
      tag: notice.tag,
      data: { link: typeof notice.link === "string" && notice.link.startsWith("/") ? notice.link : "/" },
    }),
  );
});

self.addEventListener("notificationclick", (event) => {
  event.notification.close();
  const target = `/#${event.notification.data?.link || "/"}`;
  event.waitUntil(
    self.clients.matchAll({ type: "window", includeUncontrolled: true }).then((windows) => {
      const open = windows.find((w) => new URL(w.url).origin === self.location.origin);
      if (open) return open.navigate(target).then((w) => (w || open).focus());
      return self.clients.openWindow(target);
    }),
  );
});
