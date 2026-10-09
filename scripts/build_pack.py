"""中間ファイルからパックを作る（データ形式 2）。

出力（data/packs/<pack>/）：
  pack.json        パックの版・件数・出典・ライセンスの要約
  index.json       一覧と検索と場所の絞り込みに使う小さな索引（1 種あたり数百バイト）
  species/<id>.json  種ごとの詳細（説明、節、分布コード、出典）
  synonyms.json    旧い学名 → 種の番号（検索のとき必要になってから読む）
加えて docs/ATTRIBUTION.md を自動生成し、app/sw.js の APP_VERSION を上げる。

- validate.py を通った種だけを入れる。データが無い項目は入れない（推測で埋めない）。
- 分布は地名を持たず、TDWG の地区コードだけ（地名は data/tdwg_areas.json）。索引ではビット列にして小さくする。
"""

from __future__ import annotations

import base64
import hashlib
import re
import sys

from common import DATA_DIR, DOCS_DIR, PACKS_DIR, ROOT_DIR, load_json, log, read_species_list, save_json, today, work_path
from overrides import apply_overrides
from validate import validate_species

PACK_ID = "edible-core"
PACK_TITLE = {"ja": "主要作物", "en": "Major crops"}
SCHEMA_VERSION = 2


def area_order() -> list[str]:
    areas = load_json(DATA_DIR / "tdwg_areas.json") or {"continents": []}
    return sorted({a["code"] for c in areas["continents"] for r in c["regions"] for a in r["areas"]})


def bitset(codes: list[str], index: dict[str, int]) -> str:
    bits = bytearray((len(index) + 7) // 8)
    for c in codes:
        i = index.get(c)
        if i is not None:
            bits[i >> 3] |= 1 << (i & 7)
    return base64.b64encode(bytes(bits)).decode("ascii")


def src(d: dict, *extra: str) -> dict:
    out = {k: d[k] for k in ("source", "source_url", "license", "license_url", "retrieved", "revision") if d.get(k)}
    for k in extra:
        if d.get(k) is not None:
            out[k] = d[k]
    return out


def build_record(sci: str) -> dict:
    wfo = load_json(work_path(sci, "wfo"))
    wd = load_json(work_path(sci, "wikidata")) or {}
    wp = load_json(work_path(sci, "wikipedia")) or {}
    wcup = load_json(work_path(sci, "wcup"))
    wcvp = load_json(work_path(sci, "wcvp"))
    photo = load_json(work_path(sci, "photo"))

    rec: dict = {
        "id": wfo["id"],
        "scientific_name": wfo["scientific_name"],
        "authorship": wfo.get("authorship"),
        "family": wfo.get("family"),
        # 検索用の異名は種の階級のものだけ（変種・品種レベルは数が多すぎるので入れない）
        "synonyms": sorted({s["name"] + (f" {s['authorship']}" if s.get("authorship") else "")
                            for s in wfo.get("synonyms", []) if s.get("rank") == "species"}),
        "taxonomy_source": src(wfo),
    }
    # 表示する一般名：Wikipedia の記事名を先頭に、次に Wikidata の一般名・ラベル
    names: dict[str, list[str]] = {}
    for lang, d in wp.items():
        title = d.get("title")
        if title and title.lower() != wfo["scientific_name"].lower() and title.split()[0].lower() != wfo["scientific_name"].split()[0].lower():
            names.setdefault(lang, []).append(title)
    for lang, lst in (wd.get("names") or {}).items():
        for n in lst:
            if n not in names.setdefault(lang, []):
                names[lang].append(n)
    if names:
        rec["names"] = names
        rec["names_source"] = {"source": "Wikipedia の記事名と Wikidata", "source_url": wd.get("source_url"),
                               "license": "CC0 1.0（Wikidata）。記事名は事実", "retrieved": wd.get("retrieved") or today()}
    if wd.get("qid"):
        rec["wikidata"] = wd["qid"]
    if wd.get("search_names"):
        rec["search_names"] = wd["search_names"]
    if wp:
        rec["description"] = {lang: {**src(d), "text": d["text"]} for lang, d in wp.items()}
        sections: dict = {}
        for lang, d in wp.items():
            for key, sec in (d.get("sections") or {}).items():
                sections.setdefault(key, {})[lang] = {**src(sec), "heading": sec["heading"], "text": sec["text"], "truncated": sec["truncated"]}
        if sections:
            rec["sections"] = sections
    if wcup:
        rec["edible"] = {"is_food": wcup["is_food"], "use_codes": wcup["use_codes"], **src(wcup)}
    if wcvp:
        rec["distribution"] = {"native": [e["code"] for e in wcvp["distribution"]["native"]],
                               "introduced": [e["code"] for e in wcvp["distribution"]["introduced"]], **src(wcvp)}
        raw = {k: wcvp[k] for k in ("lifeform_description", "climate_description") if wcvp.get(k)}
        if raw:
            rec["traits_raw"] = {**raw, **src(wcvp)}
    if photo:
        rec["photo"] = {k: photo[k] for k in ("file", "author", "license", "license_url", "source", "source_page",
                                              "modified", "modification", "width", "height", "retrieved")}
    # 訂正の層（data/overrides/）を最後に重ねる。元データは触らない
    return apply_overrides(rec)


INDEX_LANGS = ["ja", "en"]  # 索引に入れる名前の言語。他の言語は names/<lang>.json に分けて、必要な言語だけ読む


def index_entry(rec: dict, idx: dict[str, int]) -> dict:
    e = {"id": rec["id"], "sci": rec["scientific_name"], "fam": rec.get("family")}
    if rec.get("names"):
        e["n"] = {lang: lst[:1] for lang, lst in rec["names"].items() if lang in INDEX_LANGS}  # 表示は各言語 1 つ
    # 検索用の名前：Wikidata の別名に、表示しない 2 つ目以降の一般名（訂正で足されたものを含む）を加える
    sn = dict(rec.get("search_names") or {})
    for lang in INDEX_LANGS:
        extra = [x for x in (rec.get("names") or {}).get(lang, [])[1:] if x not in sn.get(lang, [])]
        if extra:
            sn[lang] = sn.get(lang, []) + extra
    if sn:
        e["sn"] = sn
    if rec.get("photo"):
        p = rec["photo"]
        e["p"] = {"f": p["file"], "a": p.get("author"), "l": p["license"], "lu": p["license_url"], "s": p["source"], "sp": p["source_page"], "w": p["width"], "h": p["height"]}
    ed = rec.get("edible") or {}
    e["food"] = bool(ed.get("is_food"))
    e["tox"] = "PO" in (ed.get("use_codes") or [])
    if ed.get("use_codes"):
        e["u"] = ed["use_codes"]  # 用途の印（WCUP の 10 分類）
    if rec.get("distribution"):
        e["dn"] = bitset(rec["distribution"]["native"], idx)
        e["di"] = bitset(rec["distribution"]["introduced"], idx)
    return e


def write_attribution(records: list[dict]) -> None:
    lines = ["# 写真と文章の出典・作者一覧", "",
             "このファイルはスクリプト（scripts/build_pack.py）が自動生成します。手で直さないでください。", "",
             "## 写真", "", "| 種 | 作者 | ライセンス | 元ページ | 改変 |", "|---|---|---|---|---|"]
    for r in records:
        p = r.get("photo")
        if p:
            author = p["author"] or "作者表示なし（パブリックドメイン）"
            lines.append(f"| {r['scientific_name']} | {author} | [{p['license']}]({p['license_url']}) | "
                         f"[{p['source']}]({p['source_page']}) | {p['modification']} |")
    lines += ["", "## 説明文と節", "", "| 種 | 出典 | 版 | ライセンス |", "|---|---|---|---|"]
    for r in records:
        for lang, d in (r.get("description") or {}).items():
            lines.append(f"| {r['scientific_name']} | [{d['source']}]({d['source_url']}) | {d.get('revision', '')} | [{d['license']}]({d['license_url']}) |")
        for key, per_lang in (r.get("sections") or {}).items():
            for lang, d in per_lang.items():
                lines.append(f"| {r['scientific_name']} | [{d['source']}]({d['source_url']}) | {d.get('revision', '')} | [{d['license']}]({d['license_url']}) |")
    lines += ["", "## データ", "",
              "- 学名・固定番号・異名：World Flora Online Plant List（CC0 1.0）",
              "- 各国語名：Wikipedia の記事名と Wikidata（CC0 1.0）",
              "- 食用かどうか・毒性の記録：World Checklist of Useful Plant Species, Diazgranados et al. 2020, RBG Kew（CC BY 4.0）",
              "- 分布・生活形：World Checklist of Vascular Plants, RBG Kew（CC BY 3.0）",
              "- 国と地区の対応：TDWG WGSRPD レベル 4（CC BY 4.0）、Wikidata（CC0 1.0）", ""]
    (DOCS_DIR / "ATTRIBUTION.md").write_text("\n".join(lines), encoding="utf-8")


def bump_app_version(pack_version: str) -> None:
    """app/sw.js の APP_VERSION を「パックの版.連番」に上げる。利用者の端末の保存を更新させるため。"""
    sw = ROOT_DIR / "app" / "sw.js"
    text = sw.read_text(encoding="utf-8")
    m = re.search(r'const APP_VERSION = "([\d-]+)\.(\d+)";', text)
    if not m:
        log("  app/sw.js の APP_VERSION が見つかりません（手で上げてください）")
        return
    n = int(m.group(2)) + 1 if m.group(1) == pack_version else 1
    new = f'const APP_VERSION = "{pack_version}.{n}";'
    sw.write_text(text[:m.start()] + new + text[m.end():], encoding="utf-8")
    log(f"  app/sw.js: {new}")


def main(only: list[str] | None = None) -> int:
    records, skipped = [], []
    for row in read_species_list():
        sci = row["scientific_name"]
        if only and sci not in only:
            continue
        ok, problems = validate_species(sci)
        if not ok:
            skipped.append((sci, problems))
            continue
        rec = build_record(sci)
        if rec.get("hidden"):
            log(f"  [非公開] {sci}: 訂正の層で hidden（公開から外す）")
            continue
        records.append(rec)
    # 異名の付け替えで同じ WFO 番号になった種は 1 つにまとめる（先に出たものを残す）
    seen_ids: dict[str, str] = {}
    unique = []
    for r in records:
        if r["id"] in seen_ids:
            log(f"  [重複] {r['id']} は既に取り込み済み（{seen_ids[r['id']]}）")
            continue
        seen_ids[r["id"]] = r["scientific_name"]
        unique.append(r)
    records = sorted(unique, key=lambda r: r["scientific_name"])

    areas = area_order()
    idx = {c: i for i, c in enumerate(areas)}
    pack_dir = PACKS_DIR / PACK_ID
    sp_dir = pack_dir / "species"
    sp_dir.mkdir(parents=True, exist_ok=True)
    for old in sp_dir.glob("*.json"):
        old.unlink()
    for r in records:
        save_json(sp_dir / f"{r['id']}.json", r)
    index = {"schema_version": SCHEMA_VERSION, "areas": areas, "species": [index_entry(r, idx) for r in records]}
    save_json(pack_dir / "index.json", index)
    synonyms = sorted({(s, r["id"]) for r in records for s in r.get("synonyms", [])})
    save_json(pack_dir / "synonyms.json", [[s, i] for s, i in synonyms])
    # 言語ごとの名前（索引に入れない言語）。アプリは自分の言語のファイルだけ読む
    names_dir = pack_dir / "names"
    names_dir.mkdir(exist_ok=True)
    for old in names_dir.glob("*.json"):
        old.unlink()
    per_lang: dict[str, dict[str, str]] = {}
    for r in records:
        for lang, lst in (r.get("names") or {}).items():
            if lang not in INDEX_LANGS and lst:
                per_lang.setdefault(lang, {})[r["id"]] = lst[0]
    for lang, m in per_lang.items():
        save_json(names_dir / f"{lang}.json", m)
    name_langs = sorted(per_lang)
    legacy = pack_dir / "species.json"
    if legacy.exists():
        legacy.unlink()

    digest = hashlib.sha256((pack_dir / "index.json").read_bytes()).hexdigest()
    licenses = sorted({r[k]["license"] for r in records for k in ("taxonomy_source", "edible", "distribution", "photo") if r.get(k)}
                      | {d["license"] for r in records for d in (r.get("description") or {}).values()} | {"CC0 1.0"})
    pack = {
        "id": PACK_ID, "title": PACK_TITLE, "schema_version": SCHEMA_VERSION,
        "version": today(), "built": today(), "species_count": len(records),
        "index_file": "index.json", "species_dir": "species/", "synonyms_file": "synonyms.json",
        "names_dir": "names/", "name_languages": name_langs, "index_languages": INDEX_LANGS,
        "areas_file": "../../tdwg_areas.json", "photos_dir": "../../photos/", "index_sha256": digest,
        "licenses_included": licenses,
        "sources": {
            "World Flora Online Plant List": records[0]["taxonomy_source"]["source"] if records else None,
            "Wikidata": "CC0 1.0", "Wikipedia": "CC BY-SA 4.0",
            "World Checklist of Useful Plant Species (2020)": "CC BY 4.0",
            "World Checklist of Vascular Plants": "CC BY 3.0",
            "photos": "写真ごと（species/<id>.json の photo を参照）",
        },
        "disclaimer": {"ja": "同定や利用は自己責任でお願いします。この図鑑だけを根拠に野生の植物を食べないでください。",
                       "en": "Identification and use are at your own risk. Do not eat wild plants based on this guide alone."},
    }
    save_json(pack_dir / "pack.json", pack)
    write_attribution(records)
    bump_app_version(pack["version"])
    size = (pack_dir / "index.json").stat().st_size
    log(f"パック {PACK_ID}: {len(records)} 種。索引 {size} バイト（1 種あたり {size // max(1, len(records))}）、異名 {len(synonyms)} 件、名前の言語 {len(name_langs) + len(INDEX_LANGS)}")
    for sci, problems in skipped:
        log(f"  [除外] {sci}: " + "; ".join(problems))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:] or None))
