/* pranet のオフライン用の保存係（Service Worker）。
 *
 * - 初回に、アプリ本体・画面の文字・パックのデータ・写真をまとめて端末に保存する。
 * - 以後は端末の保存を先に使い、無ければ通信する。電波が無くても動く。
 * - 新しい版を出すときは APP_VERSION を上げる。古い保存は自動で消える。
 */
const APP_VERSION = "2026-10-08.2";
const PACKS = ["edible-core"];
const CACHE = `pranet-${APP_VERSION}`;

const CORE = [
  "./", "./index.html", "./style.css", "./app.js", "./manifest.webmanifest",
  "./icons/icon-192.png", "./icons/icon-512.png",
  "../i18n/ja.json", "../i18n/en.json",
  "../data/places.json",
];

self.addEventListener("install", event => {
  event.waitUntil((async () => {
    const cache = await caches.open(CACHE);
    await cache.addAll(CORE);
    // パックごとに pack.json → species.json → 写真 の順で保存する
    for (const id of PACKS) {
      const packURL = `../data/packs/${id}/pack.json`;
      const pack = await (await fetch(packURL)).json();
      const speciesURL = `../data/packs/${id}/${pack.species_file}`;
      const species = await (await fetch(speciesURL)).json();
      await cache.addAll([packURL, speciesURL]);
      const photos = species.filter(s => s.photo).map(s => `../data/${s.photo.file}`);
      // 写真は 1 枚ずつ。失敗しても他は続ける
      await Promise.all(photos.map(async url => { try { await cache.add(url); } catch {} }));
    }
    await self.skipWaiting();
  })());
});

self.addEventListener("activate", event => {
  event.waitUntil((async () => {
    for (const key of await caches.keys()) if (key !== CACHE) await caches.delete(key);
    await self.clients.claim();
  })());
});

self.addEventListener("fetch", event => {
  const req = event.request;
  if (req.method !== "GET" || new URL(req.url).origin !== location.origin) return;
  event.respondWith((async () => {
    const cached = await caches.match(req, { ignoreSearch: true });
    if (cached) return cached;
    try {
      const res = await fetch(req);
      if (res.ok) (await caches.open(CACHE)).put(req, res.clone());
      return res;
    } catch {
      // 通信できないとき、アプリの画面だけは index.html で代替する（docs などは代替しない）
      if (req.mode === "navigate" && new URL(req.url).pathname.startsWith(new URL("./", location.href).pathname)) return caches.match("./index.html");
      throw new Error("offline");
    }
  })());
});
