"""中間ファイルからパック（data/packs/<pack>/species.json と pack.json）と docs/ATTRIBUTION.md を作る。

- validate.py を通った種だけを入れる。
- データが無い項目は入れない（空欄）。推測で埋めない。
- 形は設計図 6.3 のとおり。
"""

from __future__ import annotations

import hashlib
import json
import sys

from common import DOCS_DIR, PACKS_DIR, ROOT_DIR, SCHEMA_VERSION, load_json, log, read_species_list, save_json, today, work_path
from validate import validate_species

PACK_ID = "edible-core"
PACK_TITLE = {"ja": "主要作物", "en": "Major crops"}


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
        "synonyms": [s["name"] + (f" {s['authorship']}" if s.get("authorship") else "")
                     for s in wfo.get("synonyms", []) if s.get("rank") == "species"],
        "taxonomy_source": {"source": wfo["source"], "source_url": wfo["source_url"], "license": wfo["license"],
                            "retrieved": wfo["retrieved"]},
    }
    if wd.get("qid"):
        rec["wikidata"] = wd["qid"]
        if wd.get("names"):
            rec["names"] = wd["names"]
            rec["names_source"] = {"source": wd["source"], "source_url": wd["source_url"],
                                   "license": wd["license"], "retrieved": wd["retrieved"]}
        if wd.get("search_names"):
            rec["search_names"] = wd["search_names"]  # 検索にだけ使う（画面には出さない）
    if wp:
        rec["description"] = {
            lang: {k: d[k] for k in ("text", "source", "source_url", "revision", "license", "license_url", "retrieved")}
            for lang, d in wp.items()
        }
    if wcup:
        rec["edible"] = {
            "is_food": wcup["is_food"],
            "use_codes": wcup["use_codes"],  # WCUP の 10 分類のコード。訳はアプリ側（i18n）
            "uses": wcup["uses"],
            "source": wcup["source"], "source_url": wcup["source_url"],
            "license": wcup["license"], "retrieved": wcup["retrieved"],
        }
    if wcvp:
        rec["distribution"] = {
            "native": [e["code"] for e in wcvp["distribution"]["native"]],
            "introduced": [e["code"] for e in wcvp["distribution"]["introduced"]],
            "area_names": {e["code"]: e["area"] for k in ("native", "introduced") for e in wcvp["distribution"][k]},
            "source": wcvp["source"], "source_url": wcvp["source_url"],
            "license": wcvp["license"], "retrieved": wcvp["retrieved"],
        }
        raw = {k: wcvp[k] for k in ("lifeform_description", "climate_description") if wcvp.get(k)}
        if raw:
            rec["traits_raw"] = {**raw, "source": wcvp["source"], "source_url": wcvp["source_url"],
                                 "license": wcvp["license"], "retrieved": wcvp["retrieved"]}
    if photo:
        rec["photo"] = {k: photo[k] for k in ("file", "author", "license", "license_url", "source", "source_page",
                                              "modified", "modification", "width", "height", "retrieved")}
    return rec


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
    lines += ["", "## 説明文", "", "| 種 | 出典 | 版 | ライセンス |", "|---|---|---|---|"]
    for r in records:
        for lang, d in (r.get("description") or {}).items():
            lines.append(f"| {r['scientific_name']} | [{d['source']}]({d['source_url']}) | {d['revision']} | "
                         f"[{d['license']}]({d['license_url']}) |")
    lines += ["", "## データ", "",
              "- 学名・固定番号・異名：World Flora Online Plant List（CC0 1.0）",
              "- 各国語名：Wikidata（CC0 1.0）",
              "- 食用かどうか：World Checklist of Useful Plant Species, Diazgranados et al. 2020, RBG Kew（CC BY 4.0）",
              "- 分布・生活形：World Checklist of Vascular Plants, RBG Kew（CC BY 3.0）", ""]
    (DOCS_DIR / "ATTRIBUTION.md").write_text("\n".join(lines), encoding="utf-8")


def bump_app_version(pack_version: str) -> None:
    """app/sw.js の APP_VERSION を「パックの版.連番」に上げる。利用者の端末の保存を更新させるため。"""
    import re
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
    records = []
    skipped = []
    for row in read_species_list():
        sci = row["scientific_name"]
        if only and sci not in only:
            continue
        ok, problems = validate_species(sci)
        if not ok:
            skipped.append((sci, problems))
            continue
        records.append(build_record(sci))
    records.sort(key=lambda r: r["scientific_name"])
    pack_dir = PACKS_DIR / PACK_ID
    species_path = pack_dir / "species.json"
    save_json(species_path, records)
    digest = hashlib.sha256(species_path.read_bytes()).hexdigest()
    licenses = sorted({r[k]["license"] for r in records for k in ("taxonomy_source", "names_source", "edible", "distribution", "photo")
                       if r.get(k)} | {d["license"] for r in records for d in (r.get("description") or {}).values()})
    pack = {
        "id": PACK_ID,
        "title": PACK_TITLE,
        "schema_version": SCHEMA_VERSION,
        "version": today(),
        "built": today(),
        "species_count": len(records),
        "species_file": "species.json",
        "species_sha256": digest,
        "photos_dir": "../../photos/",
        "licenses_included": licenses,
        "sources": {
            "World Flora Online Plant List": records[0]["taxonomy_source"]["source"] if records else None,
            "Wikidata": "CC0 1.0",
            "Wikipedia": "CC BY-SA 4.0",
            "World Checklist of Useful Plant Species (2020)": "CC BY 4.0",
            "World Checklist of Vascular Plants": "CC BY 3.0",
            "photos": "写真ごと（species.json の photo を参照）",
        },
        "disclaimer": {"ja": "同定や利用は自己責任でお願いします。この図鑑だけを根拠に野生の植物を食べないでください。"},
    }
    save_json(pack_dir / "pack.json", pack)
    write_attribution(records)
    bump_app_version(pack["version"])
    log(f"パック {PACK_ID}: {len(records)} 種を書き出しました -> {species_path}")
    for sci, problems in skipped:
        log(f"  [除外] {sci}: " + "; ".join(problems))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:] or None))
