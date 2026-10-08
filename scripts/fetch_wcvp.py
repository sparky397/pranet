"""Kew の World Checklist of Vascular Plants（WCVP）から分布（自生／導入、地域別）と生活形・気候帯の記述を取る。

入力：cache/work/<種>/wfo.json（ipni_id）
出力：cache/work/<種>/wcvp.json

- wcvp.zip（names と distribution の CSV、区切りは |）を一度だけ取得する。
- まず IPNI 番号で結ぶ。無ければ学名（Accepted）で探す。同名が複数なら取り込まない。
- 地域は TDWG の level 3 コード。introduced=1 は「導入」、0 は「自生」。絶滅・疑わしい記録は除く。
"""

from __future__ import annotations

import csv
import io
import re
import sys
import zipfile

from common import CACHE_DIR, download_large, load_json, log, read_species_list, save_json, today, work_path

WCVP_DIR = CACHE_DIR / "wcvp"
WCVP_ZIP = WCVP_DIR / "wcvp.zip"
WCVP_URL = "https://sftp.kew.org/pub/data-repositories/WCVP/wcvp.zip"
WCVP_SOURCE = "World Checklist of Vascular Plants (WCVP), RBG Kew"
WCVP_SOURCE_URL = "https://powo.science.kew.org/"
WCVP_DOWNLOAD_URL = "https://sftp.kew.org/pub/data-repositories/WCVP/"
# 同梱の README_WCVP.xlsx は CC BY 3.0 と書いている。GBIF の登録情報は CC BY 4.0。
# 取得したファイルに付いている表記（3.0）に従う。どちらも「出典を表示する」条件で、pranet では使える。
WCVP_LICENSE = "CC BY 3.0"
WCVP_LICENSE_NOTE = ("同梱 README_WCVP.xlsx の表記は CC BY 3.0。GBIF 登録 "
                     "https://www.gbif.org/dataset/f382f0ce-323a-4091-bb9f-add557f3a9a2 では CC BY 4.0")


def norm_name(s: str) -> str:
    return re.sub(r"\s+", " ", s.replace("×", " ")).strip().lower()


def _reader(name: str):
    z = zipfile.ZipFile(WCVP_ZIP)
    raw = z.open(name)
    return csv.DictReader(io.TextIOWrapper(raw, encoding="utf-8", newline=""), delimiter="|")


def version_from_zip() -> str:
    with zipfile.ZipFile(WCVP_ZIP) as z:
        info = z.getinfo("wcvp_names.csv")
        y, m, d = info.date_time[:3]
        return f"{y:04d}-{m:02d}-{d:02d}"


def find_names(targets: list[dict]) -> dict[str, dict]:
    """学名 → WCVP の行（Accepted に解決済み）。1 回目で一致を探し、異名に当たった分だけ 2 回目で Accepted 行を取る。"""
    by_ipni = {t["ipni_id"]: t for t in targets if t.get("ipni_id")}
    by_name = {norm_name(t["scientific_name"]): t for t in targets}
    hits: dict[str, dict] = {}
    name_hits: dict[str, list[dict]] = {}
    for row in _reader("wcvp_names.csv"):
        t = by_ipni.get(row["ipni_id"])
        if t and t["scientific_name"] not in hits:
            hits[t["scientific_name"]] = row
        key = norm_name(row["taxon_name"])
        if key in by_name and row["taxon_status"] == "Accepted" and row["taxon_rank"] == "Species":
            name_hits.setdefault(key, []).append(row)
    for key, t in by_name.items():
        if t["scientific_name"] in hits:
            continue
        cands = name_hits.get(key, [])
        if len(cands) == 1:
            hits[t["scientific_name"]] = cands[0]
            log(f"  {t['scientific_name']}: IPNI ではなく学名で一致しました")
        elif cands:
            log(f"[ng] {t['scientific_name']}: WCVP で同名の Accepted が複数あります")
    need = {row["accepted_plant_name_id"] for row in hits.values()
            if row["accepted_plant_name_id"] and row["accepted_plant_name_id"] != row["plant_name_id"]}
    if need:
        acc_rows = {}
        for row in _reader("wcvp_names.csv"):
            if row["plant_name_id"] in need:
                acc_rows[row["plant_name_id"]] = row
        for sci, row in list(hits.items()):
            acc = row["accepted_plant_name_id"]
            if acc in acc_rows:
                log(f"  {sci}: WCVP では異名に当たったので Accepted（{acc_rows[acc]['taxon_name']}）へ付け替えます")
                hits[sci] = acc_rows[acc]
    return hits


def distributions(plant_name_ids: set[str]) -> dict[str, dict]:
    out = {pid: {"native": [], "introduced": []} for pid in plant_name_ids}
    for row in _reader("wcvp_distribution.csv"):
        pid = row["plant_name_id"]
        if pid not in out:
            continue
        if row["extinct"] == "1" or row["location_doubtful"] == "1":
            continue
        entry = {"code": row["area_code_l3"], "area": row["area"], "region": row["region"],
                 "continent": row["continent"]}
        out[pid]["introduced" if row["introduced"] == "1" else "native"].append(entry)
    for v in out.values():
        for k in ("native", "introduced"):
            v[k].sort(key=lambda e: e["code"])
    return out


def main(only: list[str] | None = None) -> None:
    download_large(WCVP_URL, WCVP_ZIP)
    version = version_from_zip()
    targets = []
    for row in read_species_list():
        sci = row["scientific_name"]
        if only and sci not in only:
            continue
        wfo = load_json(work_path(sci, "wfo"))
        if wfo:
            targets.append({"scientific_name": sci, "ipni_id": wfo.get("ipni_id"), "wfo": wfo})
    hits = find_names(targets)
    dist = distributions({r["plant_name_id"] for r in hits.values()})
    for t in targets:
        sci = t["scientific_name"]
        row = hits.get(sci)
        if not row:
            log(f"[none] {sci}: WCVP に見つかりません")
            save_json(work_path(sci, "wcvp"), None)
            continue
        d = dist[row["plant_name_id"]]
        out = {
            "wcvp_plant_name_id": row["plant_name_id"],
            "wcvp_taxon_name": row["taxon_name"],
            "wcvp_taxon_authors": row["taxon_authors"],
            "powo_id": row["powo_id"] or None,
            "lifeform_description": row["lifeform_description"] or None,
            "climate_description": row["climate_description"] or None,
            "geographic_area": row["geographic_area"] or None,
            "distribution": d,
            "source": f"{WCVP_SOURCE}, version {version}",
            "source_url": f"https://powo.science.kew.org/taxon/{row['powo_id']}" if row["powo_id"] else WCVP_SOURCE_URL,
            "download_url": WCVP_DOWNLOAD_URL,
            "license": WCVP_LICENSE,
            "license_note": WCVP_LICENSE_NOTE,
            "retrieved": today(),
        }
        save_json(work_path(sci, "wcvp"), out)
        log(f"[ok] {sci}: 自生 {len(d['native'])} 地域 / 導入 {len(d['introduced'])} 地域 "
            f"| {out['lifeform_description']} | {out['climate_description']}")


if __name__ == "__main__":
    main(sys.argv[1:] or None)
