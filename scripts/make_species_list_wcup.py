"""段階 B：WCUP（Kew の有用植物リスト）の食用種から、取り込む種を選んで species_list.csv に足す。

使い方：
  python3 scripts/make_species_list_wcup.py            上位 1000 種を足す
  python3 scripts/make_species_list_wcup.py 500        上位 500 種を足す

選び方（設計図 3 章）：
- 母集団：WCUP で用途に HF（human food）が付く種（約 7,000）。IPNI 番号で WFO の番号と学名に結ぶ。
- 順位：Wikipedia に記事がある種から。日本語版あり → 英語版あり → 記事のある言語数が多い順。
  記事の有無は Wikidata（CC0）に IPNI 番号（P961）か WFO 番号（P7715）でまとめて問い合わせる。
- 既に species_list.csv にある種（WFO 番号で照合）は除く。
- 選んだ順位の表は cache/wcup/stage_b_ranking.json に残す（なぜ選ばれたかを後から確かめられるように）。

このリストは「どの種を載せるか」を決めるためだけに使う。載せる情報はすべて他の出典から取る。
"""

from __future__ import annotations

import csv
import gzip
import sys

from common import CACHE_DIR, SCRIPTS_DIR, http_get_json, load_json, log, save_json, work_path
from fetch_wcup import WCUP_PARSED, ensure_text, parse
from fetch_wfo import IPNI_MAP_GZ, ensure_downloads, load_slim_rows

LIST = SCRIPTS_DIR / "species_list.csv"
RANKING = CACHE_DIR / "wcup" / "stage_b_ranking.json"
SPARQL = "https://query.wikidata.org/sparql"
BATCH = 150


def sparql(query: str) -> list[dict]:
    body = http_get_json(SPARQL, {"query": query, "format": "json"}, cache_name="wikidata_sparql", min_interval=1.5,
                         headers={"Accept": "application/sparql-results+json"})
    return body["results"]["bindings"]


def wikidata_articles(prop: str, keys: list[str]) -> dict[str, dict]:
    """P961（IPNI）か P7715（WFO）の値 → {qid, sitelinks, ja, en}。"""
    out: dict[str, dict] = {}
    for i in range(0, len(keys), BATCH):
        chunk = keys[i:i + BATCH]
        values = " ".join('"%s"' % k for k in chunk)
        q = f"""SELECT ?key ?item ?n ?ja ?en WHERE {{
  VALUES ?key {{ {values} }}
  ?item wdt:{prop} ?key ; wikibase:sitelinks ?n .
  OPTIONAL {{ ?ja schema:about ?item ; schema:isPartOf <https://ja.wikipedia.org/> }}
  OPTIONAL {{ ?en schema:about ?item ; schema:isPartOf <https://en.wikipedia.org/> }}
}}"""
        for b in sparql(q):
            key = b["key"]["value"]
            if int(b["n"]["value"]) == 0:
                continue  # Wikidata に項目はあるが、どの言語にも記事が無い
            rec = {"qid": b["item"]["value"].rsplit("/", 1)[-1], "sitelinks": int(b["n"]["value"]),
                   "ja": "ja" in b, "en": "en" in b}
            if key not in out or rec["sitelinks"] > out[key]["sitelinks"]:
                out[key] = rec
        log(f"  Wikidata {prop}: {min(i + BATCH, len(keys))} / {len(keys)}")
    return out


def main(limit: int = 1000) -> None:
    ensure_downloads()
    ensure_text()
    table = parse()
    food_ipni = sorted(k for k, v in table.items() if "HF" in v["codes"])
    log(f"WCUP の食用種（HF）: {len(food_ipni)}")

    ipni_to_wfo: dict[str, str] = {}
    with gzip.open(IPNI_MAP_GZ, "rt", encoding="utf-8", newline="") as f:
        next(f)
        for line in f:
            ipni, wfo = line.strip().split(",")
            ipni_to_wfo[ipni.rsplit(":", 1)[-1]] = wfo
    wfo_of = {k: ipni_to_wfo[k] for k in food_ipni if k in ipni_to_wfo}
    log(f"  WFO 番号に結べた: {len(wfo_of)}")

    # WFO の表を 1 回走査して、名前・階級・状態・受け入れ名の番号を取る（異名なら受け入れ名に付け替える）
    wanted = set(wfo_of.values())
    rows: dict[str, dict] = {}
    accepted_ids: set[str] = set()
    for r in load_slim_rows():
        if r["taxonID"] in wanted:
            rows[r["taxonID"]] = r
            if r["taxonomicStatus"] == "Synonym" and r["acceptedNameUsageID"]:
                accepted_ids.add(r["acceptedNameUsageID"])
    if accepted_ids - set(rows):
        for r in load_slim_rows():
            if r["taxonID"] in accepted_ids:
                rows[r["taxonID"]] = r

    candidates: dict[str, dict] = {}  # 受け入れ名の WFO 番号 → 候補
    for ipni, wfo in wfo_of.items():
        r = rows.get(wfo)
        if not r:
            continue
        if r["taxonomicStatus"] == "Synonym" and r["acceptedNameUsageID"] in rows:
            r = rows[r["acceptedNameUsageID"]]
        if r["taxonRank"] != "species" or r["taxonomicStatus"] != "Accepted":
            continue
        c = candidates.setdefault(r["taxonID"], {"wfo_id": r["taxonID"], "scientific_name": r["scientificName"],
                                                  "family": r["family"], "ipni": [], "wcup_name": table[ipni]["name"]})
        c["ipni"].append(ipni)
    log(f"  受け入れ名の種に定まった: {len(candidates)}")

    existing = list(csv.DictReader(LIST.open(encoding="utf-8", newline="")))
    have_ids = {e.get("wfo_id", "").strip() for e in existing if e.get("wfo_id", "").strip()}
    have_names = {e["scientific_name"] for e in existing}
    for e in existing:
        wfo = load_json(work_path(e["scientific_name"], "wfo"))
        if wfo and wfo.get("id"):
            have_ids.add(wfo["id"])

    # Wikipedia 記事の有無（Wikidata）：IPNI 番号で引き、残りを WFO 番号で引く
    all_ipni = sorted({i for c in candidates.values() for i in c["ipni"]})
    by_ipni = wikidata_articles("P961", all_ipni)
    for c in candidates.values():
        hits = [by_ipni[i] for i in c["ipni"] if i in by_ipni]
        if hits:
            c["wd"] = max(hits, key=lambda h: h["sitelinks"])
    missing = sorted(c["wfo_id"] for c in candidates.values() if "wd" not in c)
    by_wfo = wikidata_articles("P7715", missing)
    for c in candidates.values():
        if "wd" not in c and c["wfo_id"] in by_wfo:
            c["wd"] = by_wfo[c["wfo_id"]]

    ranked = sorted(candidates.values(), key=lambda c: (
        not (c.get("wd") or {}).get("ja"), not (c.get("wd") or {}).get("en"),
        -(c.get("wd") or {}).get("sitelinks", 0), c["scientific_name"]))
    with_article = sum(1 for c in ranked if c.get("wd"))
    log(f"  Wikipedia 記事あり: {with_article}（日本語版 {sum(1 for c in ranked if (c.get('wd') or {}).get('ja'))}、"
        f"英語版 {sum(1 for c in ranked if (c.get('wd') or {}).get('en'))}）")

    picked = [c for c in ranked if c["wfo_id"] not in have_ids and c["scientific_name"] not in have_names][:limit]
    save_json(RANKING, {"limit": limit, "ranked": ranked, "picked": [c["wfo_id"] for c in picked]})

    with LIST.open("w", encoding="utf-8", newline="") as f:
        w = csv.writer(f)
        w.writerow(["scientific_name", "note_ja", "wfo_id"])
        for e in existing:
            w.writerow([e["scientific_name"], e.get("note_ja", ""), e.get("wfo_id", "")])
        for c in picked:
            wd = c.get("wd") or {}
            note = "段階B：WCUP 食用（HF）" + ("、Wikipedia 日本語版あり" if wd.get("ja") else "、英語版あり" if wd.get("en") else "、記事あり" if wd else "")
            w.writerow([c["scientific_name"], note, c["wfo_id"]])
    log(f"既存 {len(existing)} 種に {len(picked)} 種を追加 → {LIST.name}。順位の表: {RANKING}")
    if picked:
        log("  先頭: " + " | ".join(c["scientific_name"] for c in picked[:5]))
        log("  末尾: " + " | ".join(c["scientific_name"] for c in picked[-3:]))


if __name__ == "__main__":
    main(int(sys.argv[1]) if len(sys.argv) > 1 else 1000)
