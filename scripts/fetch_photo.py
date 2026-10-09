"""写真を1枚選び、ライセンスを機械的に確認し、縮小して保存する。

入力：cache/work/<種>/wikidata.json（commons_images, inaturalist_taxon_id）
出力：cache/work/<種>/photo.json、data/photos/<wfo-id>.webp

優先順位：
1. Wikidata の P18 に挙がっている Wikimedia Commons の画像（ファイルごとに extmetadata でライセンス確認）
2. iNaturalist の分類群の既定写真（license_code が cc0 / cc-by のものだけ）

条件に合う写真が無ければ photo は空にする（推測で埋めない）。
"""

from __future__ import annotations

import io
import sys

from PIL import Image, ImageOps

from common import (LICENSE_URLS, PHOTOS_DIR, http_get_bytes, http_get_json, is_allowed_license,
                    load_json, log, normalize_license, read_species_list, save_json, today, work_path)

COMMONS_API = "https://commons.wikimedia.org/w/api.php"
INAT_API = "https://api.inaturalist.org/v1/taxa"
MAX_SIDE = 400      # 長辺のピクセル数（古い端末と細い回線のため小さめ）
WEBP_QUALITY = 72


def commons_candidate(filename: str) -> dict | None:
    """Commons のファイル1枚のライセンスを確認し、使えるなら情報を返す。"""
    title = "File:" + filename
    body = http_get_json(COMMONS_API, {"action": "query", "titles": title, "prop": "imageinfo",
                                       "iiprop": "url|extmetadata|size|mime",
                                       "iiurlwidth": 1024, "format": "json"},
                         cache_name="commons", min_interval=1.0)
    pages = body.get("query", {}).get("pages", {})
    for _, page in pages.items():
        info = (page.get("imageinfo") or [None])[0]
        if not info:
            return None
        if not (info.get("mime") or "").startswith("image/"):
            return None
        meta = info.get("extmetadata", {})
        short = meta.get("LicenseShortName", {}).get("value")
        lic = normalize_license(short) or normalize_license(meta.get("License", {}).get("value"))
        if not is_allowed_license(lic):
            log(f"  [commons] 使えないライセンス: {filename} -> {short!r}")
            return None
        artist_html = meta.get("Artist", {}).get("value") or ""
        artist = _strip_html(artist_html)
        if not artist and lic not in ("CC0 1.0", "Public domain"):
            log(f"  [commons] 作者名が無いので使いません: {filename}")
            return None
        return {
            "provider": "Wikimedia Commons",
            "original_title": filename,
            "download_url": info.get("thumburl") or info.get("url"),
            "author": artist or None,  # CC0 / パブリックドメインで作者表示が無い場合は空欄にする
            "license": lic,
            "license_url": meta.get("LicenseUrl", {}).get("value") or LICENSE_URLS.get(lic),
            "source_page": info.get("descriptionurl") or f"https://commons.wikimedia.org/wiki/{title}",
            "credit": _strip_html(meta.get("Credit", {}).get("value") or ""),
        }
    return None


def inat_candidate(taxon_id: str) -> dict | None:
    body = http_get_json(f"{INAT_API}/{taxon_id}", cache_name="inat", min_interval=1.0)
    results = body.get("results") or []
    if not results:
        return None
    for tp in results[0].get("taxon_photos", []) or []:
        p = tp.get("photo") or {}
        lic = normalize_license(p.get("license_code"))
        if lic not in ("CC0 1.0", "CC BY 4.0"):
            # iNaturalist の cc-by は 4.0。版が付かないので cc-by を 4.0 として扱う
            if p.get("license_code") == "cc-by":
                lic = "CC BY 4.0"
            else:
                continue
        url = (p.get("original_url") or p.get("large_url") or p.get("medium_url") or "")
        if not url:
            continue
        author = (p.get("attribution") or "").replace("(c) ", "").split(", some rights")[0].strip()
        return {
            "provider": "iNaturalist",
            "original_title": str(p.get("id")),
            "download_url": url.replace("original", "large") if "original" in url else url,
            "author": author or None,
            "license": lic,
            "license_url": LICENSE_URLS.get(lic),
            "source_page": f"https://www.inaturalist.org/photos/{p.get('id')}",
            "credit": p.get("attribution") or "",
        }
    return None


def _strip_html(s: str) -> str:
    import html
    import re
    return html.unescape(re.sub(r"\s+", " ", re.sub(r"<[^>]+>", "", s)).strip())


def save_resized(src: bytes, dest_name: str) -> dict:
    im = Image.open(io.BytesIO(src))
    im = ImageOps.exif_transpose(im).convert("RGB")
    im.thumbnail((MAX_SIDE, MAX_SIDE))
    PHOTOS_DIR.mkdir(parents=True, exist_ok=True)
    path = PHOTOS_DIR / dest_name
    im.save(path, "WEBP", quality=WEBP_QUALITY, method=6)
    return {"width": im.width, "height": im.height, "bytes": path.stat().st_size}


def main(only: list[str] | None = None) -> None:
    for row in read_species_list():
        sci = row["scientific_name"]
        if only and sci not in only:
            continue
        wfo = load_json(work_path(sci, "wfo"))
        wd = load_json(work_path(sci, "wikidata"))
        if not wfo or not wd:
            log(f"[skip] {sci}: wfo.json / wikidata.json がありません")
            continue
        cand = None
        for fn in wd.get("commons_images", []):
            cand = commons_candidate(fn)
            if cand:
                break
        if not cand and wd.get("inaturalist_taxon_id"):
            cand = inat_candidate(wd["inaturalist_taxon_id"])
        if not cand:
            log(f"[none] {sci}: 条件に合う写真がありません")
            save_json(work_path(sci, "photo"), None)
            continue
        raw = http_get_bytes(cand["download_url"], cache_name="photo_raw", min_interval=1.0)
        dest = f"{wfo['id']}.webp"
        info = save_resized(raw.read_bytes(), dest)
        out = {
            "file": f"photos/{dest}",
            "author": cand["author"],
            "license": cand["license"],
            "license_url": cand["license_url"],
            "source": cand["provider"],
            "source_page": cand["source_page"],
            "original_title": cand["original_title"],
            "modified": True,
            "modification": f"縮小（長辺 {MAX_SIDE}px 以下、WebP に変換）",
            "retrieved": today(),
            **info,
        }
        save_json(work_path(sci, "photo"), out)
        log(f"[ok] {sci}: {cand['provider']} {cand['license']} by {cand['author'] or '（作者表示なし）'} ({info['bytes']} bytes)")


if __name__ == "__main__":
    main(sys.argv[1:] or None)
