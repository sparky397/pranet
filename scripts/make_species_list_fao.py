"""FAO の WCA 2020 作物リスト（学名付き）から、取り込む種の一覧（species_list.csv）を作る。

出典：FAO Caliper, World Programme for the Census of Agriculture 2020 — Crop List
      https://www.fao.org/statistics/caliper/classifications/wca/en
      ファイル：https://storage.googleapis.com/fao-datalab-caliper/Downloads/WCA2020Crops/WCACROPS-core.csv
使い方：このリストは「どの種を載せるか」を決めるためだけに使う。載せる情報はすべて他の出典（WFO など）から取る。

- "alternative" 列の学名を取り出す。複数ある場合（; や , 区切り）は全部。
- 属名だけ（spp.）や品種群は取り込まない（種に定まらない）。
- 既存の species_list.csv の行は残し、無い学名だけ足す。
"""

from __future__ import annotations

import csv
import re

from common import CACHE_DIR, SCRIPTS_DIR, download_large, log

URL = "https://storage.googleapis.com/fao-datalab-caliper/Downloads/WCA2020Crops/WCACROPS-core.csv"
FILE = CACHE_DIR / "fao" / "WCACROPS-core.csv"
LIST = SCRIPTS_DIR / "species_list.csv"

BINOMIAL = re.compile(r"\b([A-Z][a-z]+)\s+(×\s*)?([a-z][a-z-]{2,})\b")
ABBREV = re.compile(r"\b([A-Z])\.\s+(×\s*)?([a-z][a-z-]{2,})\b")
STOP = {"spp", "sp", "var", "subsp", "ssp", "cv", "group", "and", "etc", "hybrids", "hybrid", "others", "other", "species"}


def names_from(alt: str) -> list[tuple[str, str]]:
    """'alternative' 列から (学名, 元の表記) を取り出す。"""
    out = []
    last_genus = None
    for chunk in re.split(r"[;,/]|\band\b|\bor\b", alt):
        chunk = chunk.strip()
        if not chunk:
            continue
        m = BINOMIAL.search(chunk)
        if m and m.group(3) not in STOP:
            last_genus = m.group(1)
            out.append((f"{m.group(1)} {'× ' if m.group(2) else ''}{m.group(3)}", chunk))
            continue
        m = ABBREV.search(chunk)
        if m and last_genus and m.group(1) == last_genus[0] and m.group(3) not in STOP:
            out.append((f"{last_genus} {'× ' if m.group(2) else ''}{m.group(3)}", chunk))
    return out


def main() -> None:
    download_large(URL, FILE)
    rows = list(csv.DictReader(FILE.open(encoding="utf-8-sig", newline="")))
    found: dict[str, str] = {}
    skipped = []
    for r in rows:
        alt = (r.get("alternative") or "").strip()
        names = names_from(alt)
        if not names:
            skipped.append(f"{r['code']} {r['label_en']} [{alt}]")
            continue
        for sci, _ in names:
            found.setdefault(sci, f"FAO WCA 2020 crop {r['code']} {r['label_en']}")
    existing = list(csv.DictReader(LIST.open(encoding="utf-8", newline="")))
    have = {e["scientific_name"] for e in existing}
    added = [(sci, note) for sci, note in sorted(found.items()) if sci not in have]
    with LIST.open("w", encoding="utf-8", newline="") as f:
        w = csv.writer(f)
        w.writerow(["scientific_name", "note_ja"])
        for e in existing:
            w.writerow([e["scientific_name"], e.get("note_ja", "")])
        for sci, note in added:
            w.writerow([sci, note])
    log(f"FAO の作物 {len(rows)} 品目 → 学名 {len(found)} 種。既存 {len(existing)} 種に {len(added)} 種を追加 → {LIST.name}")
    log(f"学名が取れなかった品目 {len(skipped)} 件（属名だけ・品種群など）。例: " + " | ".join(skipped[:8]))


if __name__ == "__main__":
    main()
