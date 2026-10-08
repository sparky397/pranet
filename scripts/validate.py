"""出典とライセンスが付いているか検査する。付いていないデータは取り込まない。

入力：cache/work/<種>/*.json、data/tdwg_areas.json、data/places.json
出力：画面に結果。問題があれば終了コード 1。

検査の決まり：
- wfo は必須（学名の正）。無い種はパックに入れない。
- それ以外の項目は「無くてもよい」が、あるなら source / license / retrieved が揃っていること。
- license は設計図 4 章の「使ってよいライセンス」に含まれること。
- description と節は source_url と revision が必要。photo は author（CC0/PD 以外）/ license_url / source_page と実ファイルが必要。
- 分布の地区コードは data/tdwg_areas.json にあるものだけ。places.json の地区コードも同様。
"""

from __future__ import annotations

import sys

from common import ALLOWED_LICENSES, DATA_DIR, load_json, log, read_species_list, work_path


def known_area_codes() -> set[str]:
    areas = load_json(DATA_DIR / "tdwg_areas.json") or {"continents": []}
    return {a["code"] for c in areas["continents"] for r in c["regions"] for a in r["areas"]}


def check_common(item: dict, where: str, problems: list[str], extra: tuple[str, ...] = ()) -> None:
    for key in ("source", "license", "retrieved") + extra:
        if not item.get(key):
            problems.append(f"{where}: {key} がありません")
    lic = item.get("license")
    if lic and lic not in ALLOWED_LICENSES:
        problems.append(f"{where}: 使えないライセンス {lic!r}")


def validate_species(sci: str, area_codes: set[str] | None = None) -> tuple[bool, list[str]]:
    problems: list[str] = []
    wfo = load_json(work_path(sci, "wfo"))
    if not wfo:
        return False, ["wfo がありません（学名が確定していないので取り込めません）"]
    for key in ("id", "scientific_name", "family"):
        if not wfo.get(key):
            problems.append(f"wfo: {key} がありません")
    check_common(wfo, "wfo", problems, ("source_url",))

    wd = load_json(work_path(sci, "wikidata"))
    if wd and wd.get("qid"):
        check_common(wd, "wikidata", problems, ("source_url",))

    wp = load_json(work_path(sci, "wikipedia")) or {}
    for lang, d in wp.items():
        check_common(d, f"description.{lang}", problems, ("source_url", "revision", "text", "license_url"))
        for key, sec in (d.get("sections") or {}).items():
            check_common(sec, f"sections.{key}.{lang}", problems, ("source_url", "revision", "text", "license_url", "heading"))

    wcup = load_json(work_path(sci, "wcup"))
    if wcup:
        check_common(wcup, "edible", problems, ("source_url",))
        if "is_food" not in wcup or "use_codes" not in wcup:
            problems.append("edible: is_food / use_codes がありません")

    wcvp = load_json(work_path(sci, "wcvp"))
    if wcvp:
        check_common(wcvp, "distribution", problems, ("source_url",))
        if area_codes is not None:
            unknown = {e["code"] for k in ("native", "introduced") for e in wcvp["distribution"][k]} - area_codes
            if unknown:
                problems.append(f"distribution: 地区コードが場所の一覧に無い {sorted(unknown)[:5]}")

    photo = load_json(work_path(sci, "photo"))
    if photo:
        check_common(photo, "photo", problems, ("license_url", "source_page", "file"))
        if not photo.get("author") and photo.get("license") not in ("CC0 1.0", "Public domain"):
            problems.append("photo: 作者名がありません（CC BY / CC BY-SA では必須）")
        if photo.get("file") and not (DATA_DIR / photo["file"]).exists():
            problems.append(f"photo: ファイルがありません {photo['file']}")
        if photo.get("modified") and not photo.get("modification"):
            problems.append("photo: 改変の内容（modification）がありません")
    return not problems, problems


def validate_places(area_codes: set[str]) -> list[str]:
    problems = []
    places = load_json(DATA_DIR / "places.json")
    if not places:
        return ["places.json がありません"]
    for s in places.get("sources", []):
        check_common(s, "places.sources", problems, ("source_url",))
    for c in places["continents"]:
        for k in c["countries"]:
            unknown = set(k["l3"]) - area_codes
            if unknown:
                problems.append(f"places: {k['iso']} の地区コードが場所の一覧に無い {sorted(unknown)[:5]}")
    return problems


def main(only: list[str] | None = None) -> int:
    bad = 0
    codes = known_area_codes()
    if not codes:
        log("[NG] data/tdwg_areas.json がありません（scripts/build_areas.py を実行してください）")
        bad += 1
    for row in read_species_list():
        sci = row["scientific_name"]
        if only and sci not in only:
            continue
        ok, problems = validate_species(sci, codes)
        if ok:
            log(f"[ok] {sci}")
        else:
            bad += 1
            log(f"[NG] {sci}")
            for p in problems:
                log(f"     - {p}")
    pp = validate_places(codes)
    if pp:
        bad += 1
        log("[NG] 場所の対応表")
        for p in pp:
            log(f"     - {p}")
    else:
        log("[ok] 場所の対応表")
    log(f"検査終了: 問題 {bad} 件")
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:] or None))
