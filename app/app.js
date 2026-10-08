/* pranet アプリ本体（試作品・シンプル版）。外部ライブラリなし。
 *
 * 画面は 4 つ：一覧（検索）、めくる、場所、標本箱。種を押すと詳細。
 * 詳細は上から「写真 → 名前 → 食用・気候 → 説明 → 分布」。出典は最後に 1 か所。
 * - 植物の事実はすべて species.json の出典付きデータから表示し、ここでは何も補わない。
 * - 標本箱は端末の中（localStorage）だけ。アカウントもサーバーも無い。
 */
(() => {
  "use strict";

  const PACKS = ["edible-core"];
  const DATA_BASE = "../data/";
  const REPO_URL = "https://github.com/sparky397/pranet";  // 公開後に有効
  const LANG = (new URLSearchParams(location.search).get("lang") || "ja").slice(0, 2);
  const LANGS = [LANG, "ja", "en"];
  const STORE_KEY = "pranet.box.v1";

  const $ = sel => document.querySelector(sel);
  const el = (tag, attrs = {}, ...children) => {
    const n = document.createElement(tag);
    for (const [k, v] of Object.entries(attrs)) {
      if (v == null || v === false) continue;
      if (k === "class") n.className = v;
      else if (k === "text") n.textContent = v;
      else if (k.startsWith("on")) n.addEventListener(k.slice(2), v);
      else n.setAttribute(k, v);
    }
    for (const c of children.flat()) if (c != null && c !== false) n.append(c.nodeType ? c : String(c));
    return n;
  };

  let T = {}, species = [], packs = [], places = null;
  const byId = new Map();
  let box = loadBox();

  const t = (key, vars = {}) => (T[key] || key).replace(/\{(\w+)\}/g, (_, k) => vars[k] ?? "");

  // ---------- 端末内の保存 ----------
  function loadBox() {
    try { const v = JSON.parse(localStorage.getItem(STORE_KEY) || "null"); if (v && Array.isArray(v.ids)) return v; } catch {}
    return { ids: [] };
  }
  const saveBox = () => { try { localStorage.setItem(STORE_KEY, JSON.stringify(box)); } catch {} };
  const inBox = id => box.ids.includes(id);
  const toggleBox = id => { box.ids = inBox(id) ? box.ids.filter(x => x !== id) : [...box.ids, id]; saveBox(); };

  // ---------- 読み込み ----------
  async function loadJSON(url) { const r = await fetch(url); if (!r.ok) throw new Error(`${url}: ${r.status}`); return r.json(); }
  async function init() {
    try { T = await loadJSON(`../i18n/${LANG}.json`); } catch { T = await loadJSON("../i18n/ja.json"); }
    $("#q").placeholder = t("search_placeholder");
    $("#q").setAttribute("aria-label", t("search_placeholder"));
    $("#link-attribution").textContent = t("link_attribution");
    $("#link-license").textContent = t("link_license");
    for (const id of PACKS) {
      const pack = await loadJSON(`${DATA_BASE}packs/${id}/pack.json`);
      const list = await loadJSON(`${DATA_BASE}packs/${id}/${pack.species_file}`);
      packs.push(pack);
      for (const s of list) byId.set(s.id, s);
      species.push(...list);
    }
    species.sort((a, b) => a.scientific_name.localeCompare(b.scientific_name));
    try { places = await loadJSON(`${DATA_BASE}places.json`); } catch {}
    $("#pack-info").textContent = packs.map(p => t("pack_info", { title: pick(p.title), n: p.species_count, v: p.version })).join(" / ");
    $("#disclaimer").textContent = pick(packs[0]?.disclaimer);
    let lastQ = $("#q").value;
    $("#q").addEventListener("input", () => {
      if ($("#q").value === lastQ) return;
      lastQ = $("#q").value;
      if (location.hash && location.hash !== "#/") location.hash = "#/"; else render();
    });
    $("#search-form").addEventListener("submit", e => { e.preventDefault(); location.hash = "#/"; });
    window.addEventListener("hashchange", render);
    render();
  }

  // ---------- 共通 ----------
  const norm = s => String(s).normalize("NFKC").toLowerCase()
    .replace(/[ぁ-ゖ]/g, ch => String.fromCharCode(ch.charCodeAt(0) + 0x60))
    .replace(/[×\s\-_,.;:()]+/g, " ").trim();
  const hay = s => s._hay ||= norm([s.scientific_name, ...(s.synonyms || []), ...Object.values(s.names || {}).flat()].join(" | "));
  const pick = obj => { if (!obj) return ""; for (const l of LANGS) if (obj[l]) return obj[l]; return Object.values(obj)[0] || ""; };
  const nameOf = s => { for (const l of LANGS) if (s.names?.[l]?.length) return s.names[l][0]; return null; };
  const descOf = s => { for (const l of LANGS) if (s.description?.[l]) return { lang: l, ...s.description[l] }; return null; };
  const photoURL = s => (s.photo ? DATA_BASE + s.photo.file : null);
  const speciesURL = s => `${location.origin}${location.pathname}#/species/${s.id}`;
  const link = (href, text) => el("a", { href, target: "_blank", rel: "noopener", text });

  function card(s) {
    const name = nameOf(s);
    return el("li", {}, el("a", { class: "card", href: `#/species/${s.id}` },
      s.photo ? el("img", { class: "thumb", src: photoURL(s), alt: "", loading: "lazy" }) : el("div", { class: "nophoto", text: "🌿" }),
      inBox(s.id) && el("span", { class: "heart", text: "♥" }),
      el("div", { class: "body" },
        el("div", { class: "name", text: name || s.scientific_name }),
        el("div", { class: "sci", text: name ? s.scientific_name : (s.family || "") }))));
  }
  const grid = list => el("ul", { class: "grid" }, list.map(card));

  const MODES = [["#/", "mode_list", "▦"], ["#/place", "mode_place", "⌖"], ["#/box", "mode_box", "♥"]];
  function render() {
    const main = $("#main");
    main.replaceChildren();
    document.body.classList.remove("mode-flip");
    const h = location.hash || "#/";
    const current = MODES.find(([p]) => p !== "#/" && h.startsWith(p))?.[0] || (h === "#/" ? "#/" : "");
    $("#modes").replaceChildren(...MODES.map(([href, key, ic]) => el("a", { href, class: href === current && "on" }, el("span", { class: "ic", text: ic }), t(key))));
    const m = h.match(/^#\/species\/([\w-]+)/);
    if (m && byId.has(m[1])) { renderDetail(byId.get(m[1]), main); window.scrollTo(0, 0); return; }
    if (h.startsWith("#/flip")) return renderFlip(main, h);
    if (h.startsWith("#/place")) return renderPlace(main, h);
    if (h.startsWith("#/box")) return renderBox(main);
    const q = norm($("#q").value);
    const hits = q ? species.filter(s => hay(s).includes(q)) : species;
    main.append(el("p", { class: "status", text: q ? t("results", { n: hits.length }) : t("all_species", { n: species.length }) }), grid(hits));
  }

  // ---------- めくる（場所や標本箱で絞った植物を、写真で 1 つずつ見る） ----------
  function renderFlip(main, hash) {
    document.body.classList.add("mode-flip");
    let list, back;
    if (hash.startsWith("#/flip/place")) {
      const sel = placeSelection(hash);
      list = [...sel.native, ...sel.intro];
      back = "#/place" + (hash.includes("?") ? "?" + hash.split("?")[1] : "");
    } else {
      list = box.ids.map(id => byId.get(id)).filter(Boolean);
      back = "#/box";
    }
    const counter = el("div", { class: "flip-count", text: `1 / ${list.length}` });
    main.append(el("div", { class: "flip-exit" }, el("a", { href: back, text: t("flip_exit") })), counter);
    const wrap = el("div", { class: "flip" });
    list.forEach((s, i) => {
      const d = descOf(s);
      const heart = el("button", { class: inBox(s.id) && "on", text: "♥", "aria-label": t("fav_add"), onclick: () => { toggleBox(s.id); heart.classList.toggle("on", inBox(s.id)); } });
      wrap.append(el("section", { class: "flip-card" },
        s.photo ? el("img", { src: photoURL(s), alt: s.scientific_name, loading: i < 2 ? "eager" : "lazy" }) : el("div", { class: "nophoto", text: "🌿" }),
        el("div", { class: "acts" }, heart, el("a", { href: `#/species/${s.id}`, text: "ⓘ", "aria-label": t("flip_detail") })),
        el("div", { class: "shade" },
          el("div", { class: "name", text: nameOf(s) || s.scientific_name }),
          el("div", { class: "sci", text: s.scientific_name }),
          d && el("p", { class: "fact", text: d.text.split(/(?<=[。．.!?])\s*/)[0] }),
          el("p", { class: "src" }, d && [link(d.source_url, d.source), " · "], s.photo && t("photo_credit", { author: s.photo.author || t("author_unknown") })))));
    });
    wrap.append(el("section", { class: "flip-card" }, el("div", { class: "nophoto", text: "🌱" }),
      el("div", { class: "shade" }, el("div", { class: "name", text: t("flip_end") }), el("p", {}, el("a", { href: back, text: t("flip_exit"), style: "color:#fff" })))));
    wrap.addEventListener("scroll", () => { counter.textContent = `${Math.min(Math.round(wrap.scrollTop / wrap.clientHeight) + 1, list.length)} / ${list.length}`; }, { passive: true });
    main.append(wrap);
  }
  // ---------- 場所（州 → 国） ----------
  const countryName = (() => {
    let dn = null; try { dn = new Intl.DisplayNames([LANG, "en"], { type: "region" }); } catch {}
    return iso => { try { return dn?.of(iso) || iso; } catch { return iso; } };
  })();
  // ブラウザの言語設定（例 ja-JP）から、最初に選んでおく国
  function defaultCountry() {
    if (!places) return null;
    const m = (navigator.language || "").match(/-([A-Z]{2})$/i);
    const iso = m?.[1]?.toUpperCase();
    if (!iso) return null;
    const cont = places.continents.find(c => c.countries.some(k => k.iso === iso));
    return cont ? { c: cont.code, k: iso } : null;
  }
  // 選んだ場所と、そこに自生・導入されている食用植物
  function placeSelection(hash) {
    const p = new URLSearchParams(hash.split("?")[1] || "");
    let sel = { c: p.get("c") || "", k: p.get("k") || "" };
    if (!sel.c && !hash.includes("?")) sel = defaultCountry() || sel;
    const cont = sel.c && places ? places.continents.find(c => c.code === sel.c) : null;
    const country = sel.k && cont ? cont.countries.find(k => k.iso === sel.k) : null;
    let native = [], intro = [];
    if (cont) {
      const codes = new Set((country ? country.l3 : cont.countries.flatMap(k => k.l3)));
      const has = l => l.some(c => codes.has(c));
      const food = species.filter(s => s.edible?.is_food && s.distribution);
      native = food.filter(s => has(s.distribution.native));
      intro = food.filter(s => !has(s.distribution.native) && has(s.distribution.introduced));
    }
    return { sel, cont, country, native, intro, query: `c=${sel.c}&k=${sel.k}` };
  }
  function renderPlace(main, hash) {
    main.append(el("h1", { class: "title", text: t("place_title") }));
    if (!places) return main.append(el("p", { class: "empty", text: t("no_data") }));
    const { sel, cont, native, intro, query } = placeSelection(hash);
    const go = () => { location.hash = `#/place?c=${sel.c}&k=${sel.k}`; };
    const select = (label, opts, value, onchange) => {
      const s = el("select", { "aria-label": label, onchange: e => onchange(e.target.value) },
        el("option", { value: "", text: label }), opts.map(o => el("option", { value: o.value, text: o.text })));
      s.value = value; return s;
    };
    const countries = (cont?.countries || []).map(k => ({ value: k.iso, text: countryName(k.iso) }))
      .filter(o => o.text !== o.value)  // ブラウザが国名を出せないコードは出さない
      .sort((a, b) => a.text.localeCompare(b.text, LANG));
    main.append(el("div", { class: "place-pick" },
      select(t("place_continent"), places.continents.map(c => ({ value: c.code, text: t("cont_" + c.code) })), sel.c, v => { sel.c = v; sel.k = ""; go(); }),
      cont && select(t("place_country"), countries, sel.k, v => { sel.k = v; go(); })));
    if (!cont) return main.append(el("p", { class: "status", text: t("place_help") }));
    if (native.length + intro.length > 0) main.append(el("div", { class: "btnrow" }, el("a", { class: "btn", href: `#/flip/place?${query}`, text: "⇅ " + t("flip_button") })));
    main.append(el("h2", { class: "sub", text: `${t("place_native")} · ${native.length}` }), native.length ? grid(native) : el("p", { class: "empty", text: t("place_none") }));
    main.append(el("h2", { class: "sub", text: `${t("place_introduced")} · ${intro.length}` }), intro.length ? grid(intro) : el("p", { class: "empty", text: t("place_none") }));
    main.append(el("p", { class: "src" }, t("source_prefix"), places.sources.flatMap((s, i) => [i > 0 && " · ", link(s.source_url, s.source), " · ", s.license])));
  }

  // ---------- 標本箱 ----------
  function renderBox(main) {
    const list = box.ids.map(id => byId.get(id)).filter(Boolean);
    main.append(el("p", { class: "status", text: t("box_count", { n: list.length }) }));
    main.append(el("div", { class: "btnrow" },
      list.length > 0 && el("a", { class: "btn", href: "#/flip/box", text: "⇅ " + t("flip_button") }),
      el("button", { class: "btn", text: t("box_export"), onclick: () => download(new Blob([JSON.stringify({ app: "pranet", version: 1, ids: box.ids }, null, 2)], { type: "application/json" }), "pranet-box.json") }),
      el("label", { class: "btn" }, t("box_import"), el("input", { type: "file", accept: "application/json", style: "display:none", onchange: async e => {
        try { const d = JSON.parse(await e.target.files[0].text()); for (const id of d.ids || []) if (byId.has(id) && !inBox(id)) box.ids.push(id); saveBox(); render(); } catch { alert(t("load_error")); } } }))));
    main.append(list.length ? grid(list) : el("p", { class: "empty", text: t("box_empty") }));
  }
  function download(blob, name) { const a = el("a", { href: URL.createObjectURL(blob), download: name }); document.body.append(a); a.click(); a.remove(); }

  // ---------- 共有カード ----------
  async function shareCard(s) {
    const W = 1080, H = 1350, PH = 1000;
    const cv = el("canvas", { width: W, height: H }), g = cv.getContext("2d");
    g.fillStyle = "#15170f"; g.fillRect(0, 0, W, H);
    if (s.photo) {
      const img = new Image(); img.src = photoURL(s); await img.decode();
      const r = Math.max(W / img.width, PH / img.height), w = img.width * r, h = img.height * r;
      g.drawImage(img, (W - w) / 2, (PH - h) / 2, w, h);
    }
    g.textBaseline = "top"; g.fillStyle = "#ecebe3";
    g.font = "bold 64px system-ui, sans-serif"; g.fillText(nameOf(s) || s.scientific_name, 48, PH + 36);
    g.font = "italic 40px system-ui, sans-serif"; g.fillStyle = "#c9ccbf"; g.fillText(`${s.scientific_name} · ${s.family || ""}`, 48, PH + 118);
    g.font = "28px system-ui, sans-serif"; g.fillStyle = "#a3a79a";
    if (s.photo) g.fillText(`${t("photo_credit", { author: s.photo.author || t("author_unknown") })} · ${s.photo.license} · ${s.photo.source}`, 48, PH + 190);
    g.fillText(speciesURL(s).replace(/^https?:\/\//, ""), 48, PH + 236);
    g.font = "bold 56px system-ui, sans-serif"; g.fillStyle = "#8fcf9a";
    const pw = g.measureText("p").width, x = W - 48 - g.measureText("pranet").width, y = PH + 280;
    g.fillText("ranet", x + pw, y);
    g.save(); g.translate(x + pw / 2, y + 36); g.scale(1, -1); g.textAlign = "center"; g.fillText("b", 0, -36); g.restore();
    cv.toBlob(b => download(b, `pranet-${s.id}.png`), "image/png");
  }

  // ---------- 詳細 ----------
  function renderDetail(s, main) {
    const name = nameOf(s), d = descOf(s), dist = s.distribution, climate = s.traits_raw?.climate_description;
    main.append(el("a", { class: "back", href: "#/", text: t("back") }));
    const wrap = el("div", { class: "detail" });

    // 写真
    const hero = el("div", { class: "hero" });
    hero.append(s.photo ? el("img", { src: photoURL(s), alt: s.scientific_name, width: s.photo.width, height: s.photo.height }) : el("div", { class: "nophoto", text: "🌿" }));
    hero.append(el("p", { class: "credit" }, s.photo ? [t("photo_credit", { author: s.photo.author || t("author_unknown") }), " · ", link(s.photo.license_url, s.photo.license), " · ", link(s.photo.source_page, s.photo.source)] : t("no_photo")));
    const fav = el("button", { class: `btn${inBox(s.id) ? " on" : ""}`, onclick: () => { toggleBox(s.id); fav.className = `btn${inBox(s.id) ? " on" : ""}`; fav.textContent = favText(); } });
    const favText = () => (inBox(s.id) ? "♥ " : "♡ ") + t("mode_box");
    fav.textContent = favText();
    const share = el("button", { class: "btn", text: "⤓ " + t("share_card"), onclick: async () => { share.textContent = t("share_making"); await shareCard(s); share.textContent = "⤓ " + t("share_card"); } });
    const issue = `${REPO_URL}/issues/new?title=${encodeURIComponent(`[${s.id}] ${s.scientific_name}`)}&body=${encodeURIComponent(`種: ${s.scientific_name} (${s.id})\n項目: \n間違い: \n正しい内容: \n出典（URL）: `)}`;
    hero.append(el("div", { class: "btnrow" }, fav, share, el("a", { class: "btn", href: issue, target: "_blank", rel: "noopener", text: "✎ " + t("report") })));
    wrap.append(hero);

    // 本文：名前 → 食用・気候 → 説明 → 分布 → 出典
    const body = el("div");
    body.append(el("h1", { text: name || s.scientific_name }),
      el("div", { class: "sci" }, s.scientific_name, " ", el("span", { class: "auth", text: s.authorship || "" })),
      el("div", { class: "fam", text: s.family || "" }));
    body.append(el("div", { class: "chips" },
      s.edible && el("span", { class: "tag", text: s.edible.is_food ? t("is_food_yes") : t("is_food_no") }),
      climate && el("span", { class: "tag", text: t("climate_tag", { c: climate }) })));
    body.append(el("p", { class: "warn", text: t("food_warning") }));

    body.append(section(t("description"), d
      ? [d.lang !== LANG && el("p", { class: "empty", text: t("description_other_lang", { lang: t("lang_" + d.lang) }) }), el("p", { text: d.text })]
      : el("p", { class: "empty", text: t("no_data") })));

    body.append(section(t("distribution"), dist
      ? [el("p", {}, el("strong", { text: t("native") }), ` · ${dist.native.length}`),
         dist.native.length ? el("div", { class: "areas" }, dist.native.map(c => el("span", { text: dist.area_names?.[c] || c }))) : el("p", { class: "empty", text: t("no_data") }),
         el("details", {}, el("summary", { text: `${t("introduced")} · ${dist.introduced.length}` }), el("div", { class: "areas" }, dist.introduced.map(c => el("span", { text: dist.area_names?.[c] || c }))))]
      : el("p", { class: "empty", text: t("no_data") })));

    // 出典は 1 か所にまとめる
    const srcRow = (label, src, extra) => src && el("li", {}, el("b", { text: label }), " ", src.source_url ? link(src.source_url, src.source) : src.source,
      src.license && [" · ", src.license_url ? link(src.license_url, src.license) : src.license], src.revision && ` · ${t("revision", { r: src.revision })}`, extra && [" · ", extra]);
    body.append(section(t("sources"), el("ul", { class: "srclist" },
      srcRow(t("taxonomy"), s.taxonomy_source, s.id),
      srcRow(t("names_label"), s.names_source),
      srcRow(t("description"), d),
      srcRow(t("edible"), s.edible, s.edible?.uses?.length && `${t("uses")}: ${s.edible.uses.join(", ")}`),
      srcRow(t("distribution"), dist),
      srcRow(t("traits"), s.traits_raw, s.traits_raw?.lifeform_description),
      s.photo && srcRow(t("photo_label"), { source: s.photo.source, source_url: s.photo.source_page, license: s.photo.license, license_url: s.photo.license_url }, t("photo_modified")),
      s.wikidata && el("li", {}, el("b", { text: "Wikidata" }), " ", link(`https://www.wikidata.org/wiki/${s.wikidata}`, s.wikidata))),
      s.synonyms?.length > 0 && el("details", {}, el("summary", { text: `${t("synonyms")} · ${s.synonyms.length}` }), el("ul", { class: "synlist" }, s.synonyms.map(x => el("li", { text: x }))))));

    wrap.append(body);
    main.append(wrap);
  }
  const section = (title, ...content) => el("section", { class: "block" }, el("h2", { text: title }), ...content);

  init().catch(err => { $("#status").textContent = t("load_error") + " " + err.message; console.error(err); });
})();
