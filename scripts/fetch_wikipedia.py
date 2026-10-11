"""Wikipedia から冒頭要約と、「栽培」「毒性」の節を取る。

入力：cache/work/<種>/wikidata.json（wikipedia_titles）
出力：cache/work/<種>/wikipedia.json
  { "ja": {text, title, source, source_url, revision, license, ..., "sections": {"cultivation": {...}, "toxicity": {...}}}, "en": {...} }

- 日本語版の記事があれば日本語、無ければ英語版も取る（翻訳はしない）。
- 文章は CC BY-SA 4.0。出典（記事 URL）と版 ID を必ず記録する。
- 節は本文の見出しで探す（栽培 / Cultivation、毒性 / Toxicity）。長い節は文の切れ目で短くし、続きは記事へ案内する。
- 取れないものは項目ごと省く（推測で埋めない）。
"""

from __future__ import annotations

import re
import sys
import urllib.parse

from common import http_get_json, load_json, log, read_species_list, save_json, today, work_path

LANG_ORDER = ["ja", "en"]
LANG_LABEL = {"ja": "日本語版", "en": "英語版"}
SECTION_PATTERNS = {
    "cultivation": {"ja": r"^(栽培|育て方|栽培方法|栽培法|農業)$", "en": r"^(Cultivation|Growing|Horticulture|Agriculture|Farming)$"},
    "toxicity": {"ja": r"^(毒性|毒|有毒性|毒性と安全性)$", "en": r"^(Toxicity|Poison|Poisoning|Safety|Toxicology)$"},
}
MAX_CHARS = 1800


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


def fetch_sections(lang: str, title: str, page_url: str) -> dict:
    """本文全体（見出し付きの素の文章）を取り、目的の節だけを切り出す。"""
    body = http_get_json(f"https://{lang}.wikipedia.org/w/api.php",
                         {"action": "query", "prop": "extracts|revisions", "explaintext": 1, "exsectionformat": "wiki",
                          "rvprop": "ids", "titles": title, "format": "json", "formatversion": 2},
                         cache_name=f"wikipedia_{lang}_full", min_interval=1.0)
    pages = body.get("query", {}).get("pages", [])
    if not pages or "extract" not in pages[0]:
        return {}
    text = pages[0]["extract"]
    revid = (pages[0].get("revisions") or [{}])[0].get("revid")
    heads = [(m.start(), m.end(), len(m.group(1)), m.group(2).strip()) for m in re.finditer(r"^(={2,4}) (.+?) \1$", text, re.M)]
    out = {}
    for key, pats in SECTION_PATTERNS.items():
        pat = re.compile(pats[lang]) if lang in pats else None
        if not pat:
            continue
        for i, (start, end, level, name) in enumerate(heads):
            if not pat.match(name):
                continue
            # この見出しから、同じか浅い見出しの手前まで（小見出しは含む）
            stop = len(text)
            for s2, _, l2, _ in heads[i + 1:]:
                if l2 <= level:
                    stop = s2
                    break
            section_text = text[end:stop].strip()
            section_text = re.sub(r"^={3,4} (.+?) ={3,4}$", r"■ \1", section_text, flags=re.M)  # 小見出しを印に
            section_text = re.sub(r"\n{3,}", "\n\n", section_text)
            truncated = False
            if len(section_text) > MAX_CHARS:
                cut = section_text[:MAX_CHARS]
                m = list(re.finditer(r"[。．.!?]\s", cut))
                section_text = cut[:m[-1].end()].rstrip() if m else cut
                truncated = True
            if not section_text:
                continue
            out[key] = {
                "heading": name,
                "text": section_text,
                "truncated": truncated,
                "source": f"Wikipedia {LANG_LABEL.get(lang, lang + '版')}「{title}」の節「{name}」",
                "source_url": f"{page_url}#{urllib.parse.quote(name.replace(' ', '_'))}",
                "revision": revid,
                "license": "CC BY-SA 4.0",
                "license_url": "https://creativecommons.org/licenses/by-sa/4.0/",
                "retrieved": today(),
            }
            break
    return out


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
                    try:
                        s["sections"] = fetch_sections(lang, titles[lang], s["source_url"])
                    except Exception as e:  # 節が取れなくても要約は残す（次回の実行で取り直す）
                        log(f"  [{lang}] 節を取得できません: {titles[lang]} ({str(e)[:80]})")
                        s["sections"] = {}
                    out[lang] = s
        save_json(work_path(sci, "wikipedia"), out)
        got = {k: (len(v["text"]), sorted(v["sections"].keys())) for k, v in out.items()}
        log(f"[ok] {sci}: {got if got else '説明文なし'}")


if __name__ == "__main__":
    main(sys.argv[1:] or None)
