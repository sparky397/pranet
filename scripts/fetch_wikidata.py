"""Wikidata から、WFO 番号をもとに各国語の名前と Wikipedia 記事名・写真候補を取る。

入力：cache/work/<種>/wfo.json（fetch_wfo.py の出力）
出力：cache/work/<種>/wikidata.json

- Wikidata は CC0。学名の正にはしない（各国語名と対応表にだけ使う）。
- WFO 番号（P7715）で見つからない場合だけ、学名（P225）で探し、その旨を記録する。
"""

from __future__ import annotations

import sys

from common import (http_get_json, load_json, log, read_species_list, save_json,
                    today, work_path)

API = "https://www.wikidata.org/w/api.php"
SPARQL = "https://query.wikidata.org/sparql"
LANGS = ["ja", "en"]  # 記事名と検索用の別名を取る言語（説明文を取る言語と合わせる）
# 表示用の一般名は、Wikidata にある全言語を取る（言語を足すときに取り直さなくてよいように）


def _sparql(query: str):
    return http_get_json(SPARQL, {"query": query, "format": "json"},
                         cache_name="wikidata_sparql", min_interval=1.5,
                         headers={"Accept": "application/sparql-results+json"})


def find_qid(wfo_id: str, scientific_name: str) -> tuple[str | None, str]:
    """QID と、どう見つけたか（'wfo_id' / 'scientific_name' / 'not_found'）を返す。"""
    q = 'SELECT ?item WHERE { ?item wdt:P7715 "%s" } LIMIT 5' % wfo_id
    rows = _sparql(q)["results"]["bindings"]
    if rows:
        return rows[0]["item"]["value"].rsplit("/", 1)[-1], "wfo_id"
    q = ('SELECT ?item WHERE { ?item wdt:P225 "%s" ; wdt:P31 wd:Q16521 } LIMIT 5'
         % scientific_name.replace('"', ''))
    rows = _sparql(q)["results"]["bindings"]
    if len(rows) == 1:
        return rows[0]["item"]["value"].rsplit("/", 1)[-1], "scientific_name"
    return None, "not_found"


def get_entity(qid: str) -> dict:
    body = http_get_json(API, {"action": "wbgetentities", "ids": qid, "format": "json",
                               "props": "labels|aliases|claims|sitelinks"},
                         cache_name="wikidata_entity", min_interval=1.0)
    return body["entities"][qid]


def _claim_values(entity: dict, prop: str) -> list[dict]:
    out = []
    for c in entity.get("claims", {}).get(prop, []):
        snak = c.get("mainsnak", {})
        if snak.get("snaktype") != "value":
            continue
        if c.get("rank") == "deprecated":
            continue
        out.append({"value": snak["datavalue"]["value"], "rank": c.get("rank"),
                    "qualifiers": c.get("qualifiers", {})})
    return out


def common_names(entity: dict, scientific_name: str) -> tuple[dict[str, list[str]], dict[str, list[str]]]:
    """言語ごとの名前を 2 つに分けて返す。
    names：表示用。P1843（分類群の一般名）とラベルだけ（信頼できるもの）。
    search_names：検索用。Wikidata の別名（品種名や俗称が混じるので画面には出さない）。
    学名そのもの・学名風の文字列（属名で始まる）はどちらにも入れない。学名の正は WFO。"""
    names: dict[str, list[str]] = {}
    search: dict[str, list[str]] = {lang: [] for lang in LANGS}
    genus = scientific_name.split()[0].lower()

    def clean(text: str) -> str | None:
        text = text.strip().strip(",.;").strip()
        if not text or text.lower() == scientific_name.lower() or text.split()[0].lower() == genus:
            return None
        return text

    def add(target: dict, lang: str, text: str):
        text = clean(text)
        if not text or "-" in lang and lang not in LANGS:  # 地域付きの言語コード（de-ch など）は省く
            return
        seen = {n.lower() for n in names.get(lang, [])} | {n.lower() for n in search.get(lang, [])}
        if text.lower() not in seen:
            target.setdefault(lang, []).append(text)

    for cv in _claim_values(entity, "P1843"):
        v = cv["value"]
        if isinstance(v, dict) and v.get("language"):
            add(names, v["language"], v["text"])
    for lang, lab in entity.get("labels", {}).items():
        add(names, lang, lab["value"])
    for lang in LANGS:
        for al in entity.get("aliases", {}).get(lang, []):
            add(search, lang, al["value"])
    return ({k: v for k, v in names.items() if v}, {k: v for k, v in search.items() if v})


def main(only: list[str] | None = None) -> None:
    for row in read_species_list():
        sci = row["scientific_name"]
        if only and sci not in only:
            continue
        wfo = load_json(work_path(sci, "wfo"))
        if not wfo:
            log(f"[skip] {sci}: wfo.json がありません。先に fetch_wfo.py を実行してください")
            continue
        qid, how = find_qid(wfo["id"], wfo["scientific_name"])
        if not qid:
            log(f"[none] {sci}: Wikidata に見つかりません")
            save_json(work_path(sci, "wikidata"), {"qid": None, "found_by": how, "retrieved": today()})
            continue
        ent = get_entity(qid)
        sitelinks = {lang: ent.get("sitelinks", {}).get(f"{lang}wiki", {}).get("title") for lang in LANGS}
        images = [cv["value"] for cv in _claim_values(ent, "P18")]
        names, search_names = common_names(ent, wfo["scientific_name"])
        out = {
            "qid": qid,
            "found_by": how,
            "names": names,
            "search_names": search_names,
            "wikipedia_titles": {k: v for k, v in sitelinks.items() if v},
            "commons_images": images,            # 写真候補（ライセンスは fetch_photo.py で判定）
            "gbif_id": next((cv["value"] for cv in _claim_values(ent, "P846")), None),
            "inaturalist_taxon_id": next((cv["value"] for cv in _claim_values(ent, "P3151")), None),
            "source": "Wikidata",
            "source_url": f"https://www.wikidata.org/wiki/{qid}",
            "license": "CC0 1.0",
            "retrieved": today(),
        }
        save_json(work_path(sci, "wikidata"), out)
        log(f"[ok] {sci}: {qid} ({how}) names={out['names']} wiki={out['wikipedia_titles']}")


if __name__ == "__main__":
    main(sys.argv[1:] or None)
