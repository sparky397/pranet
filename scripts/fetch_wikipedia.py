"""Wikipedia から冒頭要約と版 ID を取る。

入力：cache/work/<種>/wikidata.json（wikipedia_titles）
出力：cache/work/<種>/wikipedia.json

- 日本語版の記事があれば日本語、無ければ英語版を取る（翻訳はしない）。
- 文章は CC BY-SA 4.0。出典（記事 URL）と版 ID を必ず記録する。
- 要約が取れない言語は項目ごと省く（推測で埋めない）。
"""

from __future__ import annotations

import sys
import urllib.parse

from common import http_get_json, load_json, log, read_species_list, save_json, today, work_path

LANG_ORDER = ["ja", "en"]
LANG_LABEL = {"ja": "日本語版", "en": "英語版"}
PRIMARY_FALLBACK = True  # 日本語が無いとき英語を使う（設計図 2 章の決定）


def fetch_summary(lang: str, title: str) -> dict | None:
    url = f"https://{lang}.wikipedia.org/api/rest_v1/page/summary/{urllib.parse.quote(title, safe='')}"
    try:
        body = http_get_json(url, cache_name=f"wikipedia_{lang}", min_interval=1.0)
    except Exception as e:  # 404 など
        log(f"  [{lang}] 取得できません: {title} ({e})")
        return None
    if body.get("type") == "disambiguation":
        log(f"  [{lang}] 曖昧さ回避ページなので使いません: {title}")
        return None
    text = (body.get("extract") or "").strip()
    if not text:
        return None
    return {
        "text": text,
        "title": body.get("title") or title,
        "source": f"Wikipedia {LANG_LABEL.get(lang, lang + '版')}「{body.get('title') or title}」",
        "source_url": body.get("content_urls", {}).get("desktop", {}).get("page")
        or f"https://{lang}.wikipedia.org/wiki/{urllib.parse.quote(title)}",
        "revision": int(body["revision"]) if str(body.get("revision", "")).isdigit() else body.get("revision"),
        "timestamp": body.get("timestamp"),
        "license": "CC BY-SA 4.0",
        "license_url": "https://creativecommons.org/licenses/by-sa/4.0/",
        "retrieved": today(),
    }


def main(only: list[str] | None = None) -> None:
    for row in read_species_list():
        sci = row["scientific_name"]
        if only and sci not in only:
            continue
        wd = load_json(work_path(sci, "wikidata"))
        if not wd or not wd.get("qid"):
            log(f"[skip] {sci}: wikidata.json がありません")
            continue
        titles = wd.get("wikipedia_titles", {})
        out: dict[str, dict] = {}
        for lang in LANG_ORDER:
            if lang in titles:
                s = fetch_summary(lang, titles[lang])
                if s:
                    out[lang] = s
        save_json(work_path(sci, "wikipedia"), out)
        got = {k: len(v["text"]) for k, v in out.items()}
        log(f"[ok] {sci}: {got if got else '説明文なし'}")


if __name__ == "__main__":
    main(sys.argv[1:] or None)
