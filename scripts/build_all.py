"""データ収集を最初から最後まで順に実行する。

使い方：
  python3 scripts/build_all.py              すべての種
  python3 scripts/build_all.py "Oryza sativa"   指定の種だけ

順番は設計図 8 章「データ収集の流れ」のとおり。
"""

from __future__ import annotations

import sys

import build_pack
import fetch_photo
import fetch_wcup
import fetch_wcvp
import fetch_wfo
import fetch_wikidata
import fetch_wikipedia
import validate
from common import ensure_dirs, log


def main(only: list[str] | None = None) -> int:
    ensure_dirs()
    steps = [
        ("1. World Flora Online（学名・番号・異名）", fetch_wfo.main),
        ("2. WCUP（食用かどうか）", fetch_wcup.main),
        ("3. Wikidata（各国語名・記事名）", fetch_wikidata.main),
        ("4. Wikipedia（説明文）", fetch_wikipedia.main),
        ("5. 写真（Commons / iNaturalist）", fetch_photo.main),
        ("6. WCVP（分布・生活形）", fetch_wcvp.main),
    ]
    for title, fn in steps:
        log(f"\n=== {title} ===")
        fn(only)
    log("\n=== 7. 検査 ===")
    validate.main(only)
    log("\n=== 8. パック作成 ===")
    return build_pack.main(only)


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:] or None))
