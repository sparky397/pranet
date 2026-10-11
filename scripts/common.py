"""pranet データ収集スクリプトの共通処理。

- 取得した生データは scripts/cache/ に保存し、再実行では再取得しない。
- Wikimedia 系の API には pranet を名乗る User-Agent を付け、間隔を空けて呼ぶ。
- 事実は必ず出典付きのデータから取る。ここでは推測や補完をしない。
"""

from __future__ import annotations

import csv
import datetime as _dt
import hashlib
import json
import time
from pathlib import Path

import requests

SCRIPTS_DIR = Path(__file__).resolve().parent
ROOT_DIR = SCRIPTS_DIR.parent
CACHE_DIR = SCRIPTS_DIR / "cache"
WORK_DIR = CACHE_DIR / "work"  # 種ごとの中間ファイル
DATA_DIR = ROOT_DIR / "data"
PACKS_DIR = DATA_DIR / "packs"
PHOTOS_DIR = DATA_DIR / "photos"
DOCS_DIR = ROOT_DIR / "docs"

# 公開後はリポジトリの URL に合わせて変える。連絡先として機能する URL を含める。
USER_AGENT = "pranet/0.1 (https://github.com/sparky397/pranet; plant encyclopedia data builder)"

SCHEMA_VERSION = 1

# 使ってよいライセンス（設計図 4 章）。表記ゆれは normalize_license で吸収する。
ALLOWED_LICENSES = {"CC0 1.0", "CC BY 4.0", "CC BY 3.0", "CC BY 2.5", "CC BY 2.0",
                    "CC BY-SA 4.0", "CC BY-SA 3.0", "CC BY-SA 2.5", "CC BY-SA 2.0",
                    "Public domain"}

LICENSE_URLS = {
    "CC0 1.0": "https://creativecommons.org/publicdomain/zero/1.0/",
    "CC BY 4.0": "https://creativecommons.org/licenses/by/4.0/",
    "CC BY 3.0": "https://creativecommons.org/licenses/by/3.0/",
    "CC BY 2.5": "https://creativecommons.org/licenses/by/2.5/",
    "CC BY 2.0": "https://creativecommons.org/licenses/by/2.0/",
    "CC BY-SA 4.0": "https://creativecommons.org/licenses/by-sa/4.0/",
    "CC BY-SA 3.0": "https://creativecommons.org/licenses/by-sa/3.0/",
    "CC BY-SA 2.5": "https://creativecommons.org/licenses/by-sa/2.5/",
    "CC BY-SA 2.0": "https://creativecommons.org/licenses/by-sa/2.0/",
    "Public domain": "https://creativecommons.org/publicdomain/mark/1.0/",
}

_session = requests.Session()
_session.headers["User-Agent"] = USER_AGENT
_last_call: dict[str, float] = {}


def today() -> str:
    return _dt.date.today().isoformat()


def log(msg: str) -> None:
    print(msg, flush=True)


def ensure_dirs() -> None:
    for d in (CACHE_DIR, WORK_DIR, PACKS_DIR, PHOTOS_DIR, DOCS_DIR):
        d.mkdir(parents=True, exist_ok=True)


def read_species_list() -> list[dict]:
    with (SCRIPTS_DIR / "species_list.csv").open(encoding="utf-8", newline="") as f:
        return [row for row in csv.DictReader(f) if row.get("scientific_name")]


def slug(name: str) -> str:
    return name.strip().lower().replace(" ", "_").replace("×", "x")


def work_path(scientific_name: str, stage: str) -> Path:
    """種ごと・段階ごとの中間ファイル（JSON）の場所。"""
    d = WORK_DIR / slug(scientific_name)
    d.mkdir(parents=True, exist_ok=True)
    return d / f"{stage}.json"


def load_json(path: Path, default=None):
    if path.exists():
        with path.open(encoding="utf-8") as f:
            return json.load(f)
    return default


def save_json(path: Path, obj) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as f:
        json.dump(obj, f, ensure_ascii=False, indent=2)
        f.write("\n")


def _throttle(host: str, min_interval: float) -> None:
    now = time.monotonic()
    last = _last_call.get(host, 0.0)
    wait = min_interval - (now - last)
    if wait > 0:
        time.sleep(wait)
    _last_call[host] = time.monotonic()


def _cache_key(url: str, params: dict | None) -> str:
    raw = url + "?" + json.dumps(params or {}, sort_keys=True, ensure_ascii=False)
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:24]


def http_get_json(url: str, params: dict | None = None, *, cache_name: str,
                  min_interval: float = 1.0, headers: dict | None = None):
    """JSON を返す API を呼ぶ。応答は cache/http/<cache_name>/<hash>.json に保存する。"""
    cache_file = CACHE_DIR / "http" / cache_name / (_cache_key(url, params) + ".json")
    cached = load_json(cache_file)
    if cached is not None:
        return cached["body"]
    host = requests.utils.urlparse(url).netloc
    # 一時的な障害（時間切れ、接続切れ、5xx、429）は間を空けて 3 回まで試す。長い収集が 1 回の失敗で止まらないように
    for attempt in range(3):
        _throttle(host, min_interval)
        try:
            r = _session.get(url, params=params, headers=headers or {}, timeout=60)
            if r.status_code in (429, 500, 502, 503, 504) and attempt < 2:
                raise requests.ConnectionError(f"{r.status_code} {r.reason}")
            r.raise_for_status()
            body = r.json()
            break
        except (requests.Timeout, requests.ConnectionError, ValueError) as e:
            if attempt == 2:
                raise
            log(f"  [再試行 {attempt + 1}] {host}: {str(e)[:80]}")
            time.sleep(5 * (attempt + 1))
    save_json(cache_file, {"url": r.url, "retrieved": today(), "body": body})
    return body


def http_get_bytes(url: str, *, cache_name: str, min_interval: float = 1.0) -> Path:
    """ファイルを取得して cache/http/<cache_name>/<hash> に保存し、その場所を返す。"""
    cache_file = CACHE_DIR / "http" / cache_name / _cache_key(url, None)
    if cache_file.exists() and cache_file.stat().st_size > 0:
        return cache_file
    host = requests.utils.urlparse(url).netloc
    _throttle(host, min_interval)
    r = _session.get(url, timeout=300, stream=True)
    r.raise_for_status()
    cache_file.parent.mkdir(parents=True, exist_ok=True)
    with cache_file.open("wb") as f:
        for chunk in r.iter_content(1 << 16):
            f.write(chunk)
    return cache_file


def download_large(url: str, dest: Path) -> Path:
    """大きなダンプを一度だけ取得する。既にあれば何もしない。"""
    if dest.exists() and dest.stat().st_size > 0:
        log(f"  既にあります: {dest.name}")
        return dest
    log(f"  取得中: {url}")
    dest.parent.mkdir(parents=True, exist_ok=True)
    tmp = dest.with_suffix(dest.suffix + ".part")
    with _session.get(url, timeout=600, stream=True) as r:
        r.raise_for_status()
        with tmp.open("wb") as f:
            for chunk in r.iter_content(1 << 20):
                f.write(chunk)
    tmp.rename(dest)
    return dest


def normalize_license(text: str | None) -> str | None:
    """各データ元のライセンス表記を pranet の表記に揃える。判定できなければ None。"""
    if not text:
        return None
    t = text.strip().lower().replace("creative commons", "cc").replace("attribution", "by")
    t = t.replace("sharealike", "sa").replace("share alike", "sa").replace("share-alike", "sa")
    t = t.replace("_", " ").replace("  ", " ")
    if "nc" in t.split("-") or "noncommercial" in t or "non-commercial" in t or "-nc" in t:
        return None
    if "nd" in t.split("-") or "noderiv" in t or "-nd" in t:
        return None
    if t in ("cc0", "cc0 1.0", "cc-zero", "cc zero", "cc0-1.0", "cc0 1.0 universal", "cc0 1.0 universal public domain dedication"):
        return "CC0 1.0"
    if "cc0" in t:
        return "CC0 1.0"
    if "public domain" in t or t in ("pd", "pdm", "pd-self", "pd-old"):
        return "Public domain"
    for ver in ("4.0", "3.0", "2.5", "2.0"):
        if ("by-sa" in t or "by sa" in t) and ver in t:
            return f"CC BY-SA {ver}"
    for ver in ("4.0", "3.0", "2.5", "2.0"):
        if ("cc by" in t or "cc-by" in t) and ver in t and "sa" not in t:
            return f"CC BY {ver}"
    if t in ("cc-by", "cc by"):
        return "CC BY 4.0" if False else None  # 版が分からないものは採用しない
    return None


def is_allowed_license(normalized: str | None) -> bool:
    return normalized in ALLOWED_LICENSES
