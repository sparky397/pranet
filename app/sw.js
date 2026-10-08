/* pranet のオフライン用の保存係（Service Worker）。
 *
 * - 初回に、アプリ本体・画面の文字・索引・場所の表をまとめて端末に保存する（小さい）。
 * - 種ごとの詳細と写真は、見たとき・「まるごと保存」を押したときに保存する（大きいので先読みしない）。
 * - 以後は端末の保存を先に使い、無ければ通信する。電波が無くても動く。
 * - APP_VERSION は「パックの版.連番」。build_pack.py が自動で上げる。
 *   連番が変わるとアプリ本体の保存だけ入れ替わり、パックの版が変わると詳細と写真の保存も入れ替わる。
 */
const APP_VERSION = "2026-10-09.1";
const PACKS = ["edible-core"];
const CACHE = `pranet-app-${APP_VERSION}`;
const DATA_CACHE = `pranet-data-${APP_VERSION.split(".")[0]}`;

const CORE = [
  "./", "./index.html", "./style.css", "./app.js", "./manifest.webmanifest",
  "./icons/icon-192.png", "./icons/icon-512.png",
  "../i18n/ja.json", "../i18n/en.json",
  "../data/places.json", "../data/tdwg_areas.json",
];

self.addEventListener("install", event => {
  event.waitUntil((async () => {
    const cache = await caches.open(CACHE);
    await cache.addAll(CORE);
    for (const id of PACKS) {
      await cache.addAll([`../data/packs/${id}/pack.json`, `../data/packs/${id}/index.json`]);
    }
    await self.skipWaiting();
  })());
});

self.addEventListener("activate", event => {
  event.waitUntil((async () => {
    for (const key of await caches.keys()) if (key !== CACHE && key !== DATA_CACHE) await caches.delete(key);
    await self.clients.claim();
  })());
});

const APP_PATH = new URL("./", location.href).pathname;
function isData(url) {
  const p = new URL(url).pathname;
  return p.includes("/data/photos/") || /\/data\/packs\/[^/]+\/(species\/|synonyms\.json)/.test(p);
}

self.addEventListener("fetch", event => {
  const req = event.request;
  if (req.method !== "GET" || new URL(req.url).origin !== location.origin) return;
  event.respondWith((async () => {
    const cached = await caches.match(req, { ignoreSearch: true });
    if (cached) return cached;
    try {
      const res = await fetch(req);
      if (res.ok) (await caches.open(isData(req.url) ? DATA_CACHE : CACHE)).put(req, res.clone());
      return res;
    } catch (e) {
      // 通信できないとき、アプリの画面だけは index.html で代替する（docs などは代替しない）
      if (req.mode === "navigate" && new URL(req.url).pathname.startsWith(APP_PATH)) return caches.match("./index.html");
      throw e;
    }
  })());
});
