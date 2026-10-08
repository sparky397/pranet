"""WCVP の分布ファイルから、場所の一覧（大陸 → 地域 → 地区、TDWG level 1〜3）を作る。

出力：data/tdwg_areas.json
「場所」画面の選択肢に使う。種のデータとは独立しているので、パックに関係なく 1 つだけ持つ。
"""

from __future__ import annotations

from common import DATA_DIR, download_large, log, save_json, today
from fetch_wcvp import WCVP_LICENSE, WCVP_SOURCE, WCVP_URL, WCVP_ZIP, _reader, version_from_zip


def main() -> None:
    download_large(WCVP_URL, WCVP_ZIP)
    continents: dict[str, dict] = {}
    for row in _reader("wcvp_distribution.csv"):
        if not (row["continent_code_l1"] and row["region_code_l2"] and row["area_code_l3"]):
            continue  # 地区コードの無い行（大陸や地域だけの記録）は選択肢に入れない
        c = continents.setdefault(row["continent_code_l1"], {"code": row["continent_code_l1"], "name": row["continent"].title(), "regions": {}})
        r = c["regions"].setdefault(row["region_code_l2"], {"code": row["region_code_l2"], "name": row["region"], "areas": {}})
        r["areas"].setdefault(row["area_code_l3"], {"code": row["area_code_l3"], "name": row["area"]})
    out = {
        "source": f"{WCVP_SOURCE}, version {version_from_zip()}",
        "source_url": "https://sftp.kew.org/pub/data-repositories/WCVP/",
        "license": WCVP_LICENSE,
        "retrieved": today(),
        "scheme": "TDWG World Geographical Scheme for Recording Plant Distributions (level 1-3)",
        "continents": [
            {"code": c["code"], "name": c["name"],
             "regions": [
                 {"code": r["code"], "name": r["name"],
                  "areas": sorted(r["areas"].values(), key=lambda a: a["name"])}
                 for r in sorted(c["regions"].values(), key=lambda r: r["name"])]}
            for c in sorted(continents.values(), key=lambda c: c["code"])
        ],
    }
    n = sum(len(r["areas"]) for c in out["continents"] for r in c["regions"])
    save_json(DATA_DIR / "tdwg_areas.json", out)
    log(f"場所の一覧: 大陸 {len(out['continents'])}、地区 {n} -> data/tdwg_areas.json")


if __name__ == "__main__":
    main()
