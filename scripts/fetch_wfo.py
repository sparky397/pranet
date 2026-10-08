"""World Flora Online（Zenodo 公開版）から学名・固定番号・科・異名を取る。

入力：species_list.csv
出力：cache/work/<種>/wfo.json

- WFO の Web API は使わない（この PC から到達できないため）。Zenodo の版を一度だけ取得する。
- 学名の正は WFO だけ。入力の学名に一致する「Accepted」の種が 1 件だけのときに採用する。
  見つからない・複数ある場合は取り込まず、理由を表示する（推測で決めない）。
- species_list.csv に wfo_id 列があれば、その番号を優先する（人が確認して指定した場合）。
"""

from __future__ import annotations

import csv
import gzip
import re
import sys
import zipfile

from common import CACHE_DIR, download_large, log, read_species_list, save_json, today, work_path

WFO_VERSION = "2026-06"
WFO_RECORD = 20782718
WFO_SOURCE = f"World Flora Online Plant List {WFO_VERSION}"
WFO_SOURCE_URL = f"https://zenodo.org/records/{WFO_RECORD}"
WFO_DIR = CACHE_DIR / "wfo"
BACKBONE_ZIP = WFO_DIR / "_DwC_backbone_R.zip"
IPNI_MAP_GZ = WFO_DIR / "ipni_to_wfo.csv.gz"
SLIM_TSV = WFO_DIR / f"slim_{WFO_VERSION}.tsv"

SLIM_COLS = ["taxonID", "scientificNameID", "scientificName", "taxonRank",
             "scientificNameAuthorship", "family", "taxonomicStatus", "acceptedNameUsageID"]


def ensure_downloads() -> None:
    download_large(f"https://zenodo.org/api/records/{WFO_RECORD}/files/_DwC_backbone_R.zip/content", BACKBONE_ZIP)
    download_large(f"https://zenodo.org/api/records/{WFO_RECORD}/files/ipni_to_wfo.csv.gz/content", IPNI_MAP_GZ)


def build_slim() -> None:
    """950 MB の classification.csv から必要な列だけを抜いた小さい表を一度だけ作る。"""
    if SLIM_TSV.exists():
        return
    log("  WFO の表を小さくしています（初回のみ、数分かかります）")
    csv.field_size_limit(1 << 30)
    tmp = SLIM_TSV.with_suffix(".part")
    fallback = 0

    def lines(raw):
        """UTF-8 として読み、壊れた行だけ Latin-1 で読む（WFO の元データに混在があるため）。"""
        nonlocal fallback
        for b in raw:
            try:
                yield b.decode("utf-8")
            except UnicodeDecodeError:
                fallback += 1
                yield b.decode("latin-1")

    with zipfile.ZipFile(BACKBONE_ZIP) as z, z.open("classification.csv") as raw, \
            tmp.open("w", encoding="utf-8", newline="") as out:
        reader = csv.DictReader(lines(raw), delimiter="\t")
        writer = csv.writer(out, delimiter="\t", lineterminator="\n")
        writer.writerow(SLIM_COLS)
        n = 0
        for row in reader:
            writer.writerow([(row.get(c) or "").replace("\r", "").replace("\n", " ") for c in SLIM_COLS])
            n += 1
    tmp.rename(SLIM_TSV)
    log(f"  {n} 行を書き出しました: {SLIM_TSV.name}（文字コードの補正 {fallback} 行）")


def norm_name(s: str) -> str:
    s = s.replace("×", " ").replace(" x ", " ")
    return re.sub(r"\s+", " ", s).strip().lower()


def load_slim_rows():
    with SLIM_TSV.open(encoding="utf-8", newline="") as f:
        yield from csv.DictReader(f, delimiter="\t")


def ipni_short(lsid: str) -> str | None:
    return lsid.rsplit(":", 1)[-1] if lsid else None


def resolve(species: list[dict]) -> dict[str, dict]:
    """学名 → {候補行, 異名行} を 2 回の走査で集める。"""
    wanted = {norm_name(s["scientific_name"]): s for s in species}
    override = {s["wfo_id"].strip() for s in species if s.get("wfo_id", "").strip()}
    candidates: dict[str, list[dict]] = {k: [] for k in wanted}
    by_id: dict[str, dict] = {}
    for row in load_slim_rows():
        key = norm_name(row["scientificName"])
        if key in candidates and row["taxonRank"] == "species":
            candidates[key].append(row)
        if row["taxonID"] in override:
            by_id[row["taxonID"]] = row

    chosen: dict[str, dict] = {}
    for key, sp in wanted.items():
        sci = sp["scientific_name"]
        if sp.get("wfo_id", "").strip():
            row = by_id.get(sp["wfo_id"].strip())
            if not row:
                log(f"[ng] {sci}: 指定の wfo_id {sp['wfo_id']} が見つかりません")
                continue
            chosen[sci] = {"row": row, "how": "wfo_id"}
            continue
        accepted = [r for r in candidates[key] if r["taxonomicStatus"] == "Accepted"]
        if len(accepted) == 1:
            chosen[sci] = {"row": accepted[0], "how": "scientific_name"}
        elif not accepted:
            others = ", ".join(f"{r['scientificName']} {r['scientificNameAuthorship']} [{r['taxonomicStatus']}]"
                               for r in candidates[key]) or "候補なし"
            log(f"[ng] {sci}: Accepted の種がありません。候補: {others}")
        else:
            log(f"[ng] {sci}: Accepted が複数あります: " + ", ".join(r["taxonID"] for r in accepted))

    target_ids = {v["row"]["taxonID"] for v in chosen.values()}
    synonyms: dict[str, list[dict]] = {t: [] for t in target_ids}
    for row in load_slim_rows():
        acc = row["acceptedNameUsageID"]
        if acc in synonyms and row["taxonomicStatus"] == "Synonym":
            synonyms[acc].append(row)
    for v in chosen.values():
        v["synonyms"] = synonyms[v["row"]["taxonID"]]
    return chosen


def main(only: list[str] | None = None) -> None:
    ensure_downloads()
    build_slim()
    species = [s for s in read_species_list() if not only or s["scientific_name"] in only]
    resolved = resolve(species)
    for sp in species:
        sci = sp["scientific_name"]
        hit = resolved.get(sci)
        if not hit:
            continue
        row = hit["row"]
        out = {
            "id": row["taxonID"],
            "scientific_name": row["scientificName"],
            "authorship": row["scientificNameAuthorship"] or None,
            "family": row["family"] or None,
            "rank": row["taxonRank"],
            "status": row["taxonomicStatus"],
            "ipni_id": ipni_short(row["scientificNameID"]),
            "input_name": sci,
            "found_by": hit["how"],
            "synonyms": [
                {"id": r["taxonID"], "name": r["scientificName"],
                 "authorship": r["scientificNameAuthorship"] or None,
                 "rank": r["taxonRank"],
                 "ipni_id": ipni_short(r["scientificNameID"])}
                for r in sorted(hit["synonyms"], key=lambda r: r["scientificName"])
            ],
            "source": WFO_SOURCE,
            "source_url": WFO_SOURCE_URL,
            "wfo_version": WFO_VERSION,
            "license": "CC0 1.0",
            "retrieved": today(),
        }
        save_json(work_path(sci, "wfo"), out)
        log(f"[ok] {sci}: {out['id']} {out['scientific_name']} {out['authorship']} "
            f"({out['family']}) 異名 {len(out['synonyms'])} 件")


if __name__ == "__main__":
    main(sys.argv[1:] or None)
