/* pranet アプリ本体。外部ライブラリなし。
 *
 * 画面は 3 つ：一覧（検索）、場所、標本箱。種を押すと詳細。
 * 場所と標本箱の結果は「格子」と「大きい写真」（縦に流れる一覧。写真の下に名前・学名・撮影者・ライセンス）で切り替える。
 * - 植物の事実はすべて species.json の出典付きデータから表示し、ここでは何も補わない。
 * - 毒性の記録（WCUP の poisons）がある種には赤い ☠ を付ける。
 * - 標本箱は端末の中（localStorage）だけ。アカウントもサーバーも無い。
 * - 古い端末でも動くよう、新しすぎる書き方は避ける。
 */
(function () {
  "use strict";

  var PACKS = ["edible-core"];
  var DATA_BASE = "../data/";
  var REPO_URL = "https://github.com/sparky397/pranet";
  var LANG = (new URLSearchParams(location.search).get("lang") || "ja").slice(0, 2);
  var LANGS = [LANG, "ja", "en"];
  var STORE_KEY = "pranet.box.v1";

  var $ = function (sel) { return document.querySelector(sel); };
  function el(tag, attrs) {
    var n = document.createElement(tag);
    attrs = attrs || {};
    Object.keys(attrs).forEach(function (k) {
      var v = attrs[k];
      if (v == null || v === false) return;
      if (k === "class") n.className = v;
      else if (k === "text") n.textContent = v;
      else if (k.indexOf("on") === 0) n.addEventListener(k.slice(2), v);
      else n.setAttribute(k, v);
    });
    for (var i = 2; i < arguments.length; i++) append(n, arguments[i]);
    return n;
  }
  function append(n, c) {
    if (c == null || c === false) return;
    if (Array.isArray(c)) { c.forEach(function (x) { append(n, x); }); return; }
    n.append(c.nodeType ? c : String(c));
  }

  var T = {}, species = [], packs = [], places = null;
  var byId = new Map();
  var box = loadBox();

  var t = function (key, vars) {
    return (T[key] || key).replace(/\{(\w+)\}/g, function (_, k) { return vars && vars[k] != null ? vars[k] : ""; });
  };

  // ---------- 端末内の保存 ----------
  function loadBox() {
    try { var v = JSON.parse(localStorage.getItem(STORE_KEY) || "null"); if (v && Array.isArray(v.ids)) return v; } catch (e) {}
    return { ids: [] };
  }
  function saveBox() { try { localStorage.setItem(STORE_KEY, JSON.stringify(box)); } catch (e) {} }
  function inBox(id) { return box.ids.indexOf(id) >= 0; }
  function toggleBox(id) { box.ids = inBox(id) ? box.ids.filter(function (x) { return x !== id; }) : box.ids.concat([id]); saveBox(); }

  // ---------- 読み込み ----------
  async function loadJSON(url) { var r = await fetch(url); if (!r.ok) throw new Error(url + ": " + r.status); return r.json(); }
  async function init() {
    try { T = await loadJSON("../i18n/" + LANG + ".json"); } catch (e) { T = await loadJSON("../i18n/ja.json"); }
    $("#q").placeholder = t("search_placeholder");
    $("#q").setAttribute("aria-label", t("search_placeholder"));
    $("#link-attribution").textContent = t("link_attribution");
    $("#link-license").textContent = t("link_license");
    for (var i = 0; i < PACKS.length; i++) {
      var pack = await loadJSON(DATA_BASE + "packs/" + PACKS[i] + "/pack.json");
      var list = await loadJSON(DATA_BASE + "packs/" + PACKS[i] + "/" + pack.species_file);
      packs.push(pack);
      list.forEach(function (s) { byId.set(s.id, s); });
      species = species.concat(list);
    }
    species.sort(function (a, b) { return a.scientific_name.localeCompare(b.scientific_name); });
    try { places = await loadJSON(DATA_BASE + "places.json"); } catch (e) {}
    $("#pack-info").textContent = packs.map(function (p) { return t("pack_info", { title: pick(p.title), n: p.species_count, v: p.version }); }).join(" / ");
    $("#disclaimer").textContent = pick(packs[0] && packs[0].disclaimer);
    var lastQ = $("#q").value;
    $("#q").addEventListener("input", function () {
      if ($("#q").value === lastQ) return;
      lastQ = $("#q").value;
      if (location.hash && location.hash !== "#/") location.hash = "#/"; else render();
    });
    $("#search-form").addEventListener("submit", function (e) { e.preventDefault(); location.hash = "#/"; });
    window.addEventListener("hashchange", render);
    render();
    registerOffline();
  }

  // ---------- オフライン（保存係の登録と、新しい版の知らせ） ----------
  async function registerOffline() {
    if (!("serviceWorker" in navigator)) return;
    var info = $("#offline-info");
    try {
      var reg = await navigator.serviceWorker.register("sw.js");
      var showReady = function () { info.textContent = t("offline_ready"); };
      if (navigator.serviceWorker.controller) showReady();
      reg.addEventListener("updatefound", function () {
        var w = reg.installing;
        if (!w) return;
        w.addEventListener("statechange", function () {
          if (w.state !== "activated") return;
          if (navigator.serviceWorker.controller) {
            info.replaceChildren(t("update_available"), " ", el("a", { href: "#", text: t("reload"), onclick: function (e) { e.preventDefault(); location.reload(); } }));
          } else showReady();
        });
      });
    } catch (e) { console.warn("offline:", e); }
  }

  // ---------- 共通 ----------
  function norm(s) {
    return String(s).normalize("NFKC").toLowerCase()
      .replace(/[ぁ-ゖ]/g, function (ch) { return String.fromCharCode(ch.charCodeAt(0) + 0x60); })
      .replace(/[×\s\-_,.;:()]+/g, " ").trim();
  }
  function hay(s) {
    if (!s._hay) {
      var parts = [s.scientific_name].concat(s.synonyms || []);
      Object.keys(s.names || {}).forEach(function (l) { parts = parts.concat(s.names[l]); });
      Object.keys(s.search_names || {}).forEach(function (l) { parts = parts.concat(s.search_names[l]); });
      s._hay = norm(parts.join(" | "));
    }
    return s._hay;
  }
  function pick(obj) { if (!obj) return ""; for (var i = 0; i < LANGS.length; i++) if (obj[LANGS[i]]) return obj[LANGS[i]]; var k = Object.keys(obj); return k.length ? obj[k[0]] : ""; }
  function nameOf(s) { for (var i = 0; i < LANGS.length; i++) { var l = LANGS[i]; if (s.names && s.names[l] && s.names[l].length) return s.names[l][0]; } return null; }
  function descOf(s) { for (var i = 0; i < LANGS.length; i++) { var l = LANGS[i]; if (s.description && s.description[l]) return Object.assign({ lang: l }, s.description[l]); } return null; }
  function isToxic(s) { return !!(s.edible && s.edible.use_codes && s.edible.use_codes.indexOf("PO") >= 0); }
  function photoURL(s) { return s.photo ? DATA_BASE + s.photo.file : null; }
  function speciesURL(s) { return location.origin + location.pathname + "#/species/" + s.id; }
  function link(href, text) { return el("a", { href: href, target: "_blank", rel: "noopener", text: text }); }
  function toxMark(s, big) { return isToxic(s) ? el("span", { class: "tox" + (big ? " big" : ""), title: t("toxic_title"), "aria-label": t("toxic_title"), text: "☠" }) : null; }
  function photoCredit(s) {
    if (!s.photo) return null;
    return el("p", { class: "credit" },
      t("photo_credit", { author: s.photo.author || t("author_unknown") }), " · ",
      link(s.photo.license_url, s.photo.license), " · ",
      link(s.photo.source_page, s.photo.source),
      s.photo.modified ? " · " + t("photo_modified") : "");
  }

  function card(s) {
    var name = nameOf(s);
    return el("li", {}, el("a", { class: "card", href: "#/species/" + s.id },
      s.photo ? el("img", { class: "thumb", src: photoURL(s), alt: "", loading: "lazy" }) : el("div", { class: "nophoto", text: "🌿" }),
      inBox(s.id) ? el("span", { class: "heart", text: "♥" }) : null,
      toxMark(s),
      el("div", { class: "body" },
        el("div", { class: "name", text: name || s.scientific_name }),
        el("div", { class: "sci", text: name ? s.scientific_name : (s.family || "") }))));
  }
  function grid(list) { return el("ul", { class: "grid" }, list.map(card)); }

  // 大きい写真の一覧（Instagram 型）。写真の下に名前・学名・撮影者・ライセンス・出典
  function feedItem(s) {
    var name = nameOf(s);
    return el("article", { class: "feed-item" },
      el("a", { href: "#/species/" + s.id, class: "feed-photo" },
        s.photo ? el("img", { src: photoURL(s), alt: s.scientific_name, loading: "lazy" }) : el("div", { class: "nophoto", text: "🌿" }),
        toxMark(s, true)),
      el("div", { class: "feed-body" },
        el("a", { href: "#/species/" + s.id, class: "feed-name" }, el("strong", { text: name || s.scientific_name }), name ? el("span", { class: "sci", text: " " + s.scientific_name }) : null),
        s.family ? el("div", { class: "fam", text: s.family }) : null,
        photoCredit(s)));
  }
  function feed(list) { return el("div", { class: "feed" }, list.map(feedItem)); }
  function viewSwitch(view, base) {
    return el("div", { class: "btnrow" },
      el("a", { class: "btn" + (view !== "feed" ? " on" : ""), href: base + "v=grid", text: "▦ " + t("view_grid") }),
      el("a", { class: "btn" + (view === "feed" ? " on" : ""), href: base + "v=feed", text: "▤ " + t("view_feed") }));
  }
  function results(list, view) { return list.length ? (view === "feed" ? feed(list) : grid(list)) : el("p", { class: "empty", text: t("place_none") }); }

  var MODES = [["#/", "mode_list", "▦"], ["#/place", "mode_place", "⌖"], ["#/box", "mode_box", "♥"]];
  function render() {
    var main = $("#main");
    main.replaceChildren();
    var h = location.hash || "#/";
    var current = h === "#/" ? "#/" : (MODES.filter(function (m) { return m[0] !== "#/" && h.indexOf(m[0]) === 0; })[0] || [""])[0];
    $("#modes").replaceChildren.apply($("#modes"), MODES.map(function (m) {
      return el("a", { href: m[0], class: m[0] === current ? "on" : "" }, el("span", { class: "ic", text: m[2] }), t(m[1]));
    }));
    var m = h.match(/^#\/species\/([\w-]+)/);
    if (m && byId.has(m[1])) { renderDetail(byId.get(m[1]), main); window.scrollTo(0, 0); return; }
    if (h.indexOf("#/place") === 0) return renderPlace(main, h);
    if (h.indexOf("#/box") === 0) return renderBox(main, h);
    var q = norm($("#q").value);
    var hits = q ? species.filter(function (s) { return hay(s).indexOf(q) >= 0; }) : species;
    main.append(el("p", { class: "status", text: q ? t("results", { n: hits.length }) : t("all_species", { n: species.length }) }));
    main.append(hits.length ? grid(hits) : el("p", { class: "empty", text: t("no_results") }));
  }

  // ---------- 場所（州 → 国） ----------
  var countryName = (function () {
    var dn = null; try { dn = new Intl.DisplayNames([LANG, "en"], { type: "region" }); } catch (e) {}
    return function (iso) { try { return (dn && dn.of(iso)) || iso; } catch (e) { return iso; } };
  })();
  function defaultCountry() {
    if (!places) return null;
    var m = (navigator.language || "").match(/-([A-Z]{2})$/i);
    var iso = m && m[1] ? m[1].toUpperCase() : null;
    if (!iso) return null;
    var cont = places.continents.filter(function (c) { return c.countries.some(function (k) { return k.iso === iso; }); })[0];
    return cont ? { c: cont.code, k: iso } : null;
  }
  function params(hash) { return new URLSearchParams(hash.split("?")[1] || ""); }
  function placeSelection(hash) {
    var p = params(hash);
    var sel = { c: p.get("c") || "", k: p.get("k") || "" };
    if (!sel.c && hash.indexOf("?") < 0) sel = defaultCountry() || sel;
    var cont = sel.c && places ? places.continents.filter(function (c) { return c.code === sel.c; })[0] : null;
    var country = sel.k && cont ? cont.countries.filter(function (k) { return k.iso === sel.k; })[0] : null;
    var native = [], intro = [];
    if (cont) {
      var codes = new Set(country ? country.l3 : cont.countries.reduce(function (a, k) { return a.concat(k.l3); }, []));
      var has = function (l) { return l.some(function (c) { return codes.has(c); }); };
      var food = species.filter(function (s) { return s.edible && s.edible.is_food && s.distribution; });
      native = food.filter(function (s) { return has(s.distribution.native); });
      intro = food.filter(function (s) { return !has(s.distribution.native) && has(s.distribution.introduced); });
    }
    return { sel: sel, cont: cont, native: native, intro: intro, view: p.get("v") || "grid" };
  }
  function renderPlace(main, hash) {
    main.append(el("h1", { class: "title", text: t("place_title") }));
    if (!places) return main.append(el("p", { class: "empty", text: t("no_data") }));
    var r = placeSelection(hash), sel = r.sel, cont = r.cont;
    var base = "#/place?c=" + sel.c + "&k=" + sel.k + "&";
    var go = function () { location.hash = base + "v=" + r.view; };
    var select = function (label, opts, value, onchange) {
      var s = el("select", { "aria-label": label, onchange: function (e) { onchange(e.target.value); } },
        el("option", { value: "", text: label }), opts.map(function (o) { return el("option", { value: o.value, text: o.text }); }));
      s.value = value; return s;
    };
    var countries = (cont ? cont.countries : []).map(function (k) { return { value: k.iso, text: countryName(k.iso) }; })
      .filter(function (o) { return o.text !== o.value; })
      .sort(function (a, b) { return a.text.localeCompare(b.text, LANG); });
    main.append(el("div", { class: "place-pick" },
      select(t("place_continent"), places.continents.map(function (c) { return { value: c.code, text: t("cont_" + c.code) }; }), sel.c, function (v) { sel.c = v; sel.k = ""; go(); }),
      cont ? select(t("place_country"), countries, sel.k, function (v) { sel.k = v; go(); }) : null));
    if (!cont) return main.append(el("p", { class: "status", text: t("place_help") }));
    main.append(viewSwitch(r.view, base));
    main.append(el("h2", { class: "sub", text: t("place_native") + " · " + r.native.length }), results(r.native, r.view));
    main.append(el("h2", { class: "sub", text: t("place_introduced") + " · " + r.intro.length }), results(r.intro, r.view));
    main.append(el("p", { class: "src" }, t("source_prefix"), places.sources.map(function (s, i) { return [i > 0 ? " · " : null, link(s.source_url, s.source), " · ", s.license]; })));
  }

  // ---------- 標本箱 ----------
  function renderBox(main, hash) {
    var view = params(hash).get("v") || "grid";
    var list = box.ids.map(function (id) { return byId.get(id); }).filter(Boolean);
    main.append(el("p", { class: "status", text: t("box_count", { n: list.length }) }));
    main.append(el("div", { class: "btnrow" },
      el("button", { class: "btn", text: t("box_export"), onclick: function () { download(new Blob([JSON.stringify({ app: "pranet", format: "box", version: 1, ids: box.ids }, null, 2)], { type: "application/json" }), "pranet-box.json"); } }),
      el("label", { class: "btn" }, t("box_import"), el("input", { type: "file", accept: "application/json", style: "display:none", onchange: async function (e) {
        try { var d = JSON.parse(await e.target.files[0].text()); (d.ids || []).forEach(function (id) { if (byId.has(id) && !inBox(id)) box.ids.push(id); }); saveBox(); render(); } catch (err) { alert(t("load_error")); } } }))));
    if (!list.length) return main.append(el("p", { class: "empty", text: t("box_empty") }));
    main.append(viewSwitch(view, "#/box?"));
    main.append(results(list, view));
  }
  function download(blob, name) { var a = el("a", { href: URL.createObjectURL(blob), download: name }); document.body.append(a); a.click(); a.remove(); }

  // ---------- 共有カード ----------
  async function shareCard(s) {
    var W = 1080, H = 1350, PH = 980;
    var cv = el("canvas", { width: W, height: H }), g = cv.getContext("2d");
    g.fillStyle = "#15170f"; g.fillRect(0, 0, W, H);
    if (s.photo) {
      var img = new Image(); img.src = photoURL(s); await img.decode();
      var r = Math.max(W / img.width, PH / img.height), w = img.width * r, h = img.height * r;
      g.drawImage(img, (W - w) / 2, (PH - h) / 2, w, h);
    }
    g.textBaseline = "top"; g.fillStyle = "#ecebe3";
    g.font = "bold 64px system-ui, sans-serif"; g.fillText((isToxic(s) ? "☠ " : "") + (nameOf(s) || s.scientific_name), 48, PH + 30);
    g.font = "italic 40px system-ui, sans-serif"; g.fillStyle = "#c9ccbf"; g.fillText(s.scientific_name + " · " + (s.family || ""), 48, PH + 110);
    g.font = "26px system-ui, sans-serif"; g.fillStyle = "#a3a79a";
    if (s.photo) {
      g.fillText(t("photo_credit", { author: s.photo.author || t("author_unknown") }) + " · " + s.photo.license + " · " + t("photo_modified"), 48, PH + 176);
      g.fillText(s.photo.source + ": " + s.photo.source_page.replace(/^https?:\/\//, "").slice(0, 70), 48, PH + 214);
    }
    g.fillText(speciesURL(s).replace(/^https?:\/\//, ""), 48, PH + 252);
    g.font = "bold 56px system-ui, sans-serif"; g.fillStyle = "#8fcf9a";
    var pw = g.measureText("p").width, x = W - 48 - g.measureText("pranet").width, y = PH + 296;
    g.fillText("ranet", x + pw, y);
    g.save(); g.translate(x + pw / 2, y + 36); g.scale(1, -1); g.textAlign = "center"; g.fillText("b", 0, -36); g.restore();
    cv.toBlob(function (b) { download(b, "pranet-" + s.id + ".png"); }, "image/png");
  }

  // ---------- 詳細 ----------
  function section(title) { var sec = el("section", { class: "block" }, el("h2", { text: title })); for (var i = 1; i < arguments.length; i++) append(sec, arguments[i]); return sec; }
  function renderDetail(s, main) {
    var name = nameOf(s), d = descOf(s), dist = s.distribution, climate = s.traits_raw && s.traits_raw.climate_description;
    main.append(el("a", { class: "back", href: "#/", text: t("back") }));
    var wrap = el("div", { class: "detail" });

    var hero = el("div", { class: "hero" });
    hero.append(s.photo ? el("img", { src: photoURL(s), alt: s.scientific_name, width: s.photo.width, height: s.photo.height }) : el("div", { class: "nophoto", text: "🌿" }));
    hero.append(s.photo ? photoCredit(s) : el("p", { class: "credit", text: t("no_photo") }));
    var favText = function () { return (inBox(s.id) ? "♥ " : "♡ ") + t("mode_box"); };
    var fav = el("button", { class: "btn" + (inBox(s.id) ? " on" : ""), onclick: function () { toggleBox(s.id); fav.className = "btn" + (inBox(s.id) ? " on" : ""); fav.textContent = favText(); } });
    fav.textContent = favText();
    var share = el("button", { class: "btn", text: "⤓ " + t("share_card"), onclick: async function () { share.textContent = t("share_making"); await shareCard(s); share.textContent = "⤓ " + t("share_card"); } });
    var reportBody = "種: " + s.scientific_name + " (" + s.id + ")\n" + speciesURL(s) + "\n項目: \n間違い: \n正しい内容: \n出典（URL）: ";
    var issue = REPO_URL + "/issues/new?title=" + encodeURIComponent("[" + s.id + "] " + s.scientific_name) + "&body=" + encodeURIComponent(reportBody);
    var copy = el("button", { class: "btn", text: "✎ " + t("report_copy"), onclick: async function () { try { await navigator.clipboard.writeText(reportBody); copy.textContent = "✓ " + t("copied"); } catch (e) { alert(reportBody); } } });
    hero.append(el("div", { class: "btnrow" }, fav, share, el("a", { class: "btn", href: issue, target: "_blank", rel: "noopener", text: "✎ " + t("report") }), copy));
    wrap.append(hero);

    var body = el("div");
    body.append(el("h1", {}, name || s.scientific_name, " ", toxMark(s, true)),
      el("div", { class: "sci" }, s.scientific_name, " ", el("span", { class: "auth", text: s.authorship || "" })),
      el("div", { class: "fam", text: s.family || "" }));
    body.append(el("div", { class: "chips" },
      s.edible ? el("span", { class: "tag", text: s.edible.is_food ? t("is_food_yes") : t("is_food_no") }) : null,
      climate ? el("span", { class: "tag", text: t("climate_tag", { c: climate }) }) : null));
    if (isToxic(s)) body.append(el("p", { class: "warn tox-warn" }, el("strong", { text: "☠ " + t("toxic_title") }), " ", t("toxic_body"), " ", t("source_prefix"), link(s.edible.source_url, s.edible.source)));
    body.append(el("p", { class: "warn", text: t("food_warning") }));

    body.append(section(t("description"), d
      ? [d.lang !== LANG ? el("p", { class: "empty", text: t("description_other_lang", { lang: t("lang_" + d.lang) }) }) : null, el("p", { text: d.text })]
      : el("p", { class: "empty", text: t("no_data") })));

    var areaName = function (c) { return (dist.area_names && dist.area_names[c]) || c; };
    body.append(section(t("distribution"), dist
      ? [el("p", {}, el("strong", { text: t("native") }), " · " + dist.native.length),
         dist.native.length ? el("div", { class: "areas" }, dist.native.map(function (c) { return el("span", { text: areaName(c) }); })) : el("p", { class: "empty", text: t("no_data") }),
         el("details", {}, el("summary", { text: t("introduced") + " · " + dist.introduced.length }), el("div", { class: "areas" }, dist.introduced.map(function (c) { return el("span", { text: areaName(c) }); })))]
      : el("p", { class: "empty", text: t("no_data") })));

    var srcRow = function (label, src, extra) {
      if (!src) return null;
      return el("li", {}, el("b", { text: label }), " ", src.source_url ? link(src.source_url, src.source) : src.source,
        src.license ? [" · ", src.license_url ? link(src.license_url, src.license) : src.license] : null,
        src.revision ? " · " + t("revision", { r: src.revision }) : null, extra ? [" · ", extra] : null);
    };
    var usesText = s.edible && s.edible.use_codes ? s.edible.use_codes.map(function (c) { return t("use_" + c); }).join(", ") : null;
    body.append(section(t("sources"), el("ul", { class: "srclist" },
      srcRow(t("taxonomy"), s.taxonomy_source, s.id),
      srcRow(t("names_label"), s.names_source),
      srcRow(t("description"), d),
      srcRow(t("edible"), s.edible, usesText ? t("uses") + ": " + usesText : null),
      srcRow(t("distribution"), dist),
      srcRow(t("traits"), s.traits_raw, s.traits_raw && s.traits_raw.lifeform_description),
      s.photo ? srcRow(t("photo_label"), { source: s.photo.source, source_url: s.photo.source_page, license: s.photo.license, license_url: s.photo.license_url }, t("photo_modified")) : null,
      s.wikidata ? el("li", {}, el("b", { text: "Wikidata" }), " ", link("https://www.wikidata.org/wiki/" + s.wikidata, s.wikidata)) : null),
      s.synonyms && s.synonyms.length ? el("details", {}, el("summary", { text: t("synonyms") + " · " + s.synonyms.length }), el("ul", { class: "synlist" }, s.synonyms.map(function (x) { return el("li", { text: x }); }))) : null));

    wrap.append(body);
    main.append(wrap);
  }

  init().catch(function (err) { $("#status").textContent = t("load_error") + " " + err.message; console.error(err); });
})();
