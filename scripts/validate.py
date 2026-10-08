"""出典とライセンスが付いているか検査する。付いていないデータは取り込まない。

入力：cache/work/<種>/*.json
出力：画面に結果。問題があれば終了コード 1。

検査の決まり：
- wfo は必須（学名の正）。無い種はパックに入れない。
- それ以外の項目は「無くてもよい」が、あるなら source / license / retrieved が揃っていること。
- license は設計図 4 章の「使ってよいライセンス」に含まれること。
- description は source_url と revision が必要。photo は author / license_url / source_page と実ファイルが必要。
"""

from __future__ import annotations

import sys

from common import ALLOWED_LICENSES, DATA_DIR, load_json, log, read_species_list, work_path


def check_common(item: dict, where: str, problems: list[str], extra: tuple[str, ...] = ()) -> None:
    for key in ("source", "license", "retrieved") + extra:
        if not item.get(key):
            problems.append(f"{where}: {key} がありません")
    lic = item.get("license")
    if lic and lic not in ALLOWED_LICENSES:
        problems.append(f"{where}: 使えないライセンス {lic!r}")


def validate_species(sci: str) -> tuple[bool, list[str]]:
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

    wcup = load_json(work_path(sci, "wcup"))
    if wcup:
        check_common(wcup, "edible", problems, ("source_url",))
        if "is_food" not in wcup:
            problems.append("edible: is_food がありません")

    wcvp = load_json(work_path(sci, "wcvp"))
    if wcvp:
        check_common(wcvp, "distribution", problems, ("source_url",))

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


def main(only: list[str] | None = None) -> int:
    bad = 0
    for row in read_species_list():
        sci = row["scientific_name"]
        if only and sci not in only:
            continue
        ok, problems = validate_species(sci)
        if ok:
            log(f"[ok] {sci}")
        else:
            bad += 1
            log(f"[NG] {sci}")
            for p in problems:
                log(f"     - {p}")
    log(f"検査終了: 問題のある種 {bad} 件")
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:] or None))
