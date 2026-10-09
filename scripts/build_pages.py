"""検索エンジンに載るための、種ごとの静的ページを作る（docs/世界一への道筋.md 4.1）。

出力：
  p/<番号>.html   名前・学名・写真・説明の冒頭・出典・アプリへのリンク。外部の部品なし
  sitemap.xml     全ページの一覧
  robots.txt

- 中身はパック（data/packs/*/species/*.json）から機械的に作る。推測で書き足さない。
- 1 項目 1 URL（設計図 9 章）。ページを開くと、本文の上にアプリで開くリンクがある。
"""

from __future__ import annotations

import html
import json

from common import PACKS_DIR, ROOT_DIR, log

SITE = "https://sparky397.github.io/pranet"
PAGES_DIR = ROOT_DIR / "p"
LANG_ORDER = ["ja", "en"]


def esc(s) -> str:
    return html.escape(str(s or ""), quote=True)


def first(obj: dict | None, keys=LANG_ORDER):
    if not obj:
        return None, None
    for k in keys:
        if obj.get(k):
            return k, obj[k]
    k = next(iter(obj))
    return k, obj[k]


def page(rec: dict) -> str:
    name_lang, names = first(rec.get("names"))
    name = names[0] if names else None
    d_lang, d = first(rec.get("description"))
    photo = rec.get("photo")
    title = f"{name} ({rec['scientific_name']})" if name else rec["scientific_name"]
    summary = (d["text"][:160] + "…") if d and len(d["text"]) > 160 else (d["text"] if d else "")
    tox = "PO" in ((rec.get("edible") or {}).get("use_codes") or [])
    app_url = f"{SITE}/app/#/species/{rec['id']}"
    img = f"{SITE}/data/{photo['file']}" if photo else f"{SITE}/app/icons/icon-512.png"
    srcs = []
    srcs.append(("学名", rec["taxonomy_source"]))
    if rec.get("names_source"):
        srcs.append(("名前", rec["names_source"]))
    if d:
        srcs.append(("説明", d))
    if rec.get("edible"):
        srcs.append(("食用・毒性", rec["edible"]))
    if rec.get("distribution"):
        srcs.append(("分布", rec["distribution"]))
    src_html = "".join(
        f'<li>{esc(label)}: <a href="{esc(s.get("source_url"))}">{esc(s.get("source"))}</a> · '
        f'<a href="{esc(s.get("license_url") or "#")}">{esc(s.get("license"))}</a></li>' for label, s in srcs)
    photo_html = ""
    if photo:
        photo_html = (f'<figure><img src="../data/{esc(photo["file"])}" alt="{esc(rec["scientific_name"])}" width="{photo["width"]}" height="{photo["height"]}">'
                      f'<figcaption>撮影: {esc(photo.get("author") or "作者表示なし")} · <a href="{esc(photo["license_url"])}">{esc(photo["license"])}</a> · '
                      f'<a href="{esc(photo["source_page"])}">{esc(photo["source"])}</a> · 縮小あり</figcaption></figure>')
    sci_syn = ", ".join(rec.get("synonyms", [])[:20])
    return f"""<!doctype html>
<html lang="{esc(name_lang or 'ja')}">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{esc(title)} - pranet</title>
<meta name="description" content="{esc(summary)}">
<link rel="canonical" href="{SITE}/p/{esc(rec['id'])}.html">
<meta property="og:title" content="{esc(title)}">
<meta property="og:description" content="{esc(summary)}">
<meta property="og:image" content="{esc(img)}">
<meta property="og:type" content="article">
<meta property="og:url" content="{SITE}/p/{esc(rec['id'])}.html">
<meta name="twitter:card" content="summary_large_image">
<link rel="icon" href="../app/icons/icon-192.png">
<style>
body{{margin:0;font-family:system-ui,sans-serif;line-height:1.55;color:#1d1f1a;background:#fbfaf7}}
main{{max-width:720px;margin:0 auto;padding:16px}}
img{{max-width:100%;height:auto;border-radius:12px}}
figcaption,small,.src{{font-size:.85rem;color:#6a6e63}}
.sci{{font-style:italic}} .tox{{color:#c0392b;font-weight:700}}
.btn{{display:inline-block;background:#2f6b3a;color:#fff;padding:10px 16px;border-radius:999px;text-decoration:none}}
@media(prefers-color-scheme:dark){{body{{background:#15170f;color:#ecebe3}}figcaption,small,.src{{color:#a3a79a}}}}
</style>
</head>
<body>
<main>
<p><a href="../app/">pranet</a> · 出典付きの植物図鑑</p>
<h1>{esc(name or rec['scientific_name'])}{' <span class="tox" title="毒性の記録あり">☠</span>' if tox else ''}</h1>
<p class="sci">{esc(rec['scientific_name'])} {esc(rec.get('authorship') or '')} · {esc(rec.get('family') or '')}</p>
{photo_html}
<p>{esc(d['text']) if d else '説明：情報なし'}</p>
{('<p class="src">出典: <a href="' + esc(d['source_url']) + '">' + esc(d['source']) + '</a> · ' + esc(d['license']) + '</p>') if d else ''}
<p><a class="btn" href="{esc(app_url)}">図鑑で開く（分布・栽培・毒性・出典）</a></p>
{('<p><small>異名: <span class="sci">' + esc(sci_syn) + '</span></small></p>') if sci_syn else ''}
<p class="src">同定や利用は自己責任でお願いします。この図鑑だけを根拠に野生の植物を食べないでください。</p>
<h2>出典</h2>
<ul class="src">{src_html}</ul>
<p class="src">このページは pranet のデータから自動生成しています。コードは MIT、データは項目ごとのライセンス（<a href="../docs/LICENSE-DATA.md">説明</a>）。</p>
</main>
</body>
</html>
"""


def main() -> None:
    PAGES_DIR.mkdir(exist_ok=True)
    for old in PAGES_DIR.glob("*.html"):
        old.unlink()
    urls = [f"{SITE}/", f"{SITE}/app/"]
    n = 0
    for pack_dir in sorted(PACKS_DIR.iterdir()):
        sp_dir = pack_dir / "species"
        if not sp_dir.is_dir():
            continue
        for f in sorted(sp_dir.glob("*.json")):
            rec = json.loads(f.read_text(encoding="utf-8"))
            (PAGES_DIR / f"{rec['id']}.html").write_text(page(rec), encoding="utf-8")
            urls.append(f"{SITE}/p/{rec['id']}.html")
            n += 1
    (ROOT_DIR / "sitemap.xml").write_text(
        '<?xml version="1.0" encoding="UTF-8"?>\n<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">\n'
        + "".join(f"  <url><loc>{esc(u)}</loc></url>\n" for u in urls) + "</urlset>\n", encoding="utf-8")
    (ROOT_DIR / "robots.txt").write_text(f"User-agent: *\nAllow: /\nSitemap: {SITE}/sitemap.xml\n", encoding="utf-8")
    log(f"種ごとのページ {n} 件 -> p/、sitemap.xml（{len(urls)} URL）、robots.txt")


if __name__ == "__main__":
    main()
