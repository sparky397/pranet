"""訂正の層 data/overrides/（設計図 15.3）。

元データ（自動で取り直す）に、出典付きの訂正を重ねて公開データにする。
- 1 種 1 ファイル：data/overrides/<WFO番号>.json
- 訂正は追記のみ。取り消しは status を "retracted" にした記録を足す（消さない）。
- field は下の FIELDS にあるものだけ。source_url と license は必須。
使い方は docs/訂正の提案のしかた.md。
"""

from __future__ import annotations

import json

from common import ALLOWED_LICENSES, DATA_DIR, LICENSE_URLS, load_json

OVERRIDES_DIR = DATA_DIR / "overrides"

# 受け付ける項目と、その値の形
FIELDS = {
    "names.<lang>": "list",          # 表示する一般名（その言語）。文字列の配列。先頭が主表示
    "description.<lang>": "text",    # 説明文（その言語）。{"text": "…"}
    "edible.is_food": "bool",        # 食用の記録（true / false）
    "edible.use_codes": "list",      # 用途コードの配列（HF, AF, ME, MA, EU, GS, PO, SU, FU, IF）
    "distribution.native": "list",   # 自生の地区コード（TDWG レベル 3）の配列
    "distribution.introduced": "list",
    "hidden": "bool",                # true なら公開から外す（削除ではない）
}
USE_CODES = {"HF", "AF", "ME", "MA", "EU", "GS", "PO", "SU", "FU", "IF"}
STATUSES = {"accepted", "retracted"}
REQUIRED = ("field", "value", "source", "source_url", "license", "date", "status")


def field_kind(field: str) -> str | None:
    if field in FIELDS:
        return FIELDS[field]
    head, _, lang = field.partition(".")
    if head in ("names", "description") and lang and lang.isalpha() and len(lang) <= 3:
        return FIELDS[head + ".<lang>"]
    return None


def path_for(wfo_id: str):
    return OVERRIDES_DIR / f"{wfo_id}.json"


def load_overrides(wfo_id: str) -> list[dict]:
    doc = load_json(path_for(wfo_id))
    return list(doc.get("overrides") or []) if isinstance(doc, dict) else []


def apply_overrides(rec: dict) -> dict:
    """accepted の訂正を順に当てる。当てた記録を rec["corrections"] に残す（画面の出典欄に出す）。"""
    entries = [o for o in load_overrides(rec["id"]) if o.get("status") == "accepted"]
    if not entries:
        return rec
    corrections = []
    for o in entries:
        field, value = o["field"], o["value"]
        head, _, sub = field.partition(".")
        if field == "hidden":
            rec["hidden"] = bool(value)
        elif head == "names":
            rec.setdefault("names", {})[sub] = list(value)
        elif head == "description":
            prev = (rec.get("description") or {}).get(sub) or {}
            rec.setdefault("description", {})[sub] = {**prev, "text": value["text"], "source": o["source"],
                                                       "source_url": o["source_url"], "license": o["license"],
                                                       "license_url": LICENSE_URLS.get(o["license"]), "retrieved": o["date"]}
            rec["description"][sub].pop("revision", None)
        elif head == "edible":
            rec.setdefault("edible", {})[sub] = value
        elif head == "distribution":
            rec.setdefault("distribution", {})[sub] = list(value)
        corrections.append({"field": field, "source": o["source"], "source_url": o["source_url"], "license": o["license"],
                            "license_url": LICENSE_URLS.get(o["license"]), "proposer": o.get("proposer") or None,
                            "date": o["date"]})
    rec["corrections"] = corrections
    return rec


def validate_overrides(known_ids: set[str], area_codes: set[str]) -> list[str]:
    """訂正ファイルの検査。問題を文字列の一覧で返す（0 件なら問題なし）。"""
    problems: list[str] = []
    if not OVERRIDES_DIR.exists():
        return problems
    for path in sorted(OVERRIDES_DIR.glob("*.json")):
        where = f"overrides/{path.name}"
        try:
            doc = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError) as e:
            problems.append(f"{where}: JSON として読めません（{e}）")
            continue
        wfo_id = path.stem
        if not isinstance(doc, dict) or doc.get("id") != wfo_id:
            problems.append(f"{where}: id がファイル名（{wfo_id}）と一致しません")
            continue
        if wfo_id not in known_ids:
            problems.append(f"{where}: この WFO 番号の種は species_list にありません")
        for i, o in enumerate(doc.get("overrides") or []):
            tag = f"{where} #{i + 1}"
            if not isinstance(o, dict):
                problems.append(f"{tag}: 項目が辞書ではありません")
                continue
            for k in REQUIRED:
                if k not in o or o[k] in ("", None):
                    problems.append(f"{tag}: {k} がありません")
            if o.get("status") not in STATUSES:
                problems.append(f"{tag}: status は accepted か retracted です")
            if not str(o.get("source_url", "")).startswith("http"):
                problems.append(f"{tag}: source_url は URL（http…）です")
            if o.get("license") and o["license"] not in ALLOWED_LICENSES:
                problems.append(f"{tag}: license {o['license']!r} は受け付けられません（{', '.join(sorted(ALLOWED_LICENSES))}）")
            kind = field_kind(str(o.get("field", "")))
            if kind is None:
                problems.append(f"{tag}: field {o.get('field')!r} は受け付けられません（{', '.join(FIELDS)}）")
                continue
            v = o.get("value")
            if kind == "bool" and not isinstance(v, bool):
                problems.append(f"{tag}: value は true / false です")
            elif kind == "list" and not (isinstance(v, list) and all(isinstance(x, str) and x for x in v)):
                problems.append(f"{tag}: value は文字列の配列です")
            elif kind == "text" and not (isinstance(v, dict) and isinstance(v.get("text"), str) and v["text"].strip()):
                problems.append(f'{tag}: value は {{"text": "…"}} です')
            if kind == "list" and isinstance(v, list):
                if o["field"] == "edible.use_codes" and set(v) - USE_CODES:
                    problems.append(f"{tag}: 用途コードが不正です {sorted(set(v) - USE_CODES)}")
                if str(o["field"]).startswith("distribution.") and area_codes and set(v) - area_codes:
                    problems.append(f"{tag}: 地区コードが tdwg_areas.json にありません {sorted(set(v) - area_codes)[:5]}")
    return problems
