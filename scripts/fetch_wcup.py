"""Kew の World Checklist of Useful Plant Species（WCUP, 2020）から「食用かどうか」を取る。

入力：cache/work/<種>/wfo.json（ipni_id、synonyms）
出力：cache/work/<種>/wcup.json

- WCUP は PDF（CC BY 4.0）でしか公開されていない。pdftotext（poppler-utils）で文字にして読む。
  1 行目が「学名 著者」、次の行が「IPNI番号 | 用途コード | CWR | [出典番号]」という並び。
- IPNI 番号で WFO と結ぶ（名前の照合はしない）。異名の IPNI 番号でも探す。
- この出典には「どの部分を食べるか」は無いので、parts は入れない（空欄）。
"""

from __future__ import annotations

import gzip
import re
import shutil
import subprocess
import sys

from common import CACHE_DIR, download_large, load_json, log, read_species_list, save_json, today, work_path
from fetch_wfo import IPNI_MAP_GZ

WCUP_DIR = CACHE_DIR / "wcup"
WCUP_PDF = WCUP_DIR / "World_Checklist_of_Useful_Plant_Species_2020.pdf"
WCUP_TXT = WCUP_DIR / "wcup_2020_raw.txt"
WCUP_PARSED = WCUP_DIR / "wcup_2020_parsed.json"
WCUP_PDF_URL = "https://kew.iro.bl.uk/bitstreams/a78c5dee-2467-4c1b-b46f-78cf322fd309/download"
WCUP_SOURCE = "World Checklist of Useful Plant Species (Diazgranados et al. 2020, RBG Kew)"
WCUP_SOURCE_URL = "https://doi.org/10.5063/F1CV4G34"

USE_CODES = {  # PDF 冒頭の凡例（Level 1 categories）
    "HF": "human food", "AF": "animal food", "ME": "medicines", "MA": "materials",
    "EU": "environmental uses", "GS": "gene sources", "PO": "poisons", "SU": "social uses",
    "FU": "fuels", "IF": "invertebrate food",
}
DATA_LINE = re.compile(r"^\s*(\d+-\d+)\s*\|\s*([A-Z ]*?)\s*(?:\|\s*(CWR))?\s*(?:\|\s*\[.*)?\s*$")


def ensure_text() -> None:
    download_large(WCUP_PDF_URL, WCUP_PDF)
    if WCUP_TXT.exists():
        return
    if not shutil.which("pdftotext"):
        raise SystemExit("pdftotext が必要です（Ubuntu: sudo apt install poppler-utils）")
    subprocess.run(["pdftotext", "-raw", str(WCUP_PDF), str(WCUP_TXT)], check=True)


def parse() -> dict[str, dict]:
    """IPNI 番号 → {name, codes, cwr} の表。一度作ったら保存して使い回す。"""
    cached = load_json(WCUP_PARSED)
    if cached:
        return cached
    table: dict[str, dict] = {}
    prev = ""
    with WCUP_TXT.open(encoding="utf-8") as f:
        for line in f:
            line = line.rstrip("\n")
            m = DATA_LINE.match(line)
            if m and prev and not DATA_LINE.match(prev):
                ipni, codes, cwr = m.group(1), m.group(2).split(), bool(m.group(3))
                table[ipni] = {"name": prev.strip(), "codes": codes, "cwr": cwr}
            if line.strip():
                prev = line
    save_json(WCUP_PARSED, table)
    log(f"  WCUP から {len(table)} 件の用途を読み取りました")
    return table


def wfo_to_ipni() -> dict[str, set[str]]:
    rev: dict[str, set[str]] = {}
    with gzip.open(IPNI_MAP_GZ, "rt", encoding="utf-8", newline="") as f:
        next(f)
        for line in f:
            ipni, wfo = line.strip().split(",")
            rev.setdefault(wfo, set()).add(ipni.rsplit(":", 1)[-1])
    return rev


def main(only: list[str] | None = None) -> None:
    ensure_text()
    table = parse()
    rev = wfo_to_ipni()
    for row in read_species_list():
        sci = row["scientific_name"]
        if only and sci not in only:
            continue
        wfo = load_json(work_path(sci, "wfo"))
        if not wfo:
            log(f"[skip] {sci}: wfo.json がありません")
            continue
        ids = [wfo["id"]] + [s["id"] for s in wfo.get("synonyms", [])]
        ipnis: list[str] = []
        for i in ([wfo.get("ipni_id")] + [s.get("ipni_id") for s in wfo.get("synonyms", [])]):
            if i and i not in ipnis:
                ipnis.append(i)
        for wid in ids:
            for i in sorted(rev.get(wid, ())):
                if i not in ipnis:
                    ipnis.append(i)
        hit = next(((i, table[i]) for i in ipnis if i in table), None)
        if not hit:
            log(f"[none] {sci}: WCUP に見つかりません（探した IPNI: {ipnis[:5]}…）")
            save_json(work_path(sci, "wcup"), None)
            continue
        ipni, entry = hit
        out = {
            "is_food": "HF" in entry["codes"],
            "use_codes": entry["codes"],
            "uses": [USE_CODES.get(c, c) for c in entry["codes"]],
            "crop_wild_relative": entry["cwr"],
            "matched_name": entry["name"],
            "matched_ipni_id": ipni,
            "source": WCUP_SOURCE,
            "source_url": WCUP_SOURCE_URL,
            "license": "CC BY 4.0",
            "retrieved": today(),
        }
        save_json(work_path(sci, "wcup"), out)
        log(f"[ok] {sci}: {'食用' if out['is_food'] else '食用でない'} {entry['codes']} ({entry['name']})")


if __name__ == "__main__":
    main(sys.argv[1:] or None)
