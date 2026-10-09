"""「州 → 国」で場所を選ぶための対応表を作る。

出力：data/places.json
  6 つの州（アジア、アフリカ、ヨーロッパ、北アメリカ、南アメリカ、オセアニア）
  → 国（ISO 3166-1 の 2 文字コード）→ その国を含む TDWG レベル 3 の地区コード

データ元：
- TDWG World Geographical Scheme for Recording Plant Distributions（WGSRPD）レベル 4 の表。
  レベル 4 の単位ごとに ISO の国コードが付いている。CC BY 4.0。
- Wikidata：国 → 大陸（P30）。CC0。複数の大陸にまたがる国は、下の表で決める。
- data/tdwg_areas.json（WCVP 由来）：Wikidata に無い地域の州を、TDWG の大陸から決めるために使う。

国名は持たない。アプリ側でブラウザの機能（Intl.DisplayNames）を使って各国語で表示する。
"""

from __future__ import annotations

from common import DATA_DIR, download_large, http_get_json, load_json, log, save_json, today, CACHE_DIR

TDWG_URL = "https://raw.githubusercontent.com/tdwg/wgsrpd/master/109-488-1-ED/2nd%20Edition/tblLevel4.txt"
TDWG_FILE = CACHE_DIR / "tdwg" / "tblLevel4.txt"
TDWG_SOURCE = "TDWG World Geographical Scheme for Recording Plant Distributions, 2nd ed., level 4"
TDWG_SOURCE_URL = "https://www.tdwg.org/standards/wgsrpd/"
SPARQL = "https://query.wikidata.org/sparql"

CONTINENTS = ["asia", "africa", "europe", "north_america", "south_america", "oceania"]
WD_CONTINENT = {"Q48": "asia", "Q15": "africa", "Q46": "europe", "Q49": "north_america",
                "Q18": "south_america", "Q538": "oceania", "Q55643": "oceania"}
# TDWG に残っている古い国コード → 今のコード。PI（西沙諸島）は国に対応しないので外す
ISO_RENAME = {"BU": "MM", "TP": "TL", "YU": "RS"}
ISO_DROP = {"PI"}

# 複数の大陸にまたがる国の扱い（地理の慣用に従う）
TIE_BREAK = {"RU": "europe", "TR": "asia", "KZ": "asia", "CY": "asia", "EG": "africa", "AZ": "asia", "GE": "asia",
             "AM": "asia", "KI": "oceania", "PW": "oceania", "SB": "oceania", "TV": "oceania", "UM": "oceania",
             "TF": "africa", "ID": "asia", "PA": "north_america", "TT": "south_america"}
# Wikidata に無い地域コードの保険：TDWG の大陸（レベル 1）→ 州
TDWG_L1 = {"1": "europe", "2": "africa", "3": "asia", "4": "asia", "5": "oceania", "6": "oceania",
           "7": "north_america", "8": "south_america"}


def wikidata_continents() -> dict[str, set[str]]:
    q = "SELECT ?iso ?cont WHERE { ?c wdt:P297 ?iso ; wdt:P30 ?cont . FILTER NOT EXISTS { ?c wdt:P576 ?d } }"
    body = http_get_json(SPARQL, {"query": q, "format": "json"}, cache_name="wikidata_sparql", min_interval=1.5,
                         headers={"Accept": "application/sparql-results+json"})
    out: dict[str, set[str]] = {}
    for b in body["results"]["bindings"]:
        qid = b["cont"]["value"].rsplit("/", 1)[-1]
        if qid in WD_CONTINENT:
            out.setdefault(b["iso"]["value"].upper(), set()).add(WD_CONTINENT[qid])
    return out


def main() -> None:
    download_large(TDWG_URL, TDWG_FILE)
    areas = load_json(DATA_DIR / "tdwg_areas.json") or {"continents": []}
    l3_to_l1 = {a["code"]: c["code"] for c in areas["continents"] for r in c["regions"] for a in r["areas"]}
    known_l3 = set(l3_to_l1)

    country_l3: dict[str, set[str]] = {}
    with TDWG_FILE.open(encoding="utf-8", errors="replace") as f:
        header = next(f)
        for line in f:
            parts = line.rstrip("\r\n").split("*")
            if len(parts) < 4:
                continue
            l3, iso = parts[2].strip(), parts[3].strip().upper()
            iso = ISO_RENAME.get(iso, iso)
            if iso and l3 and l3 in known_l3 and iso not in ISO_DROP:
                country_l3.setdefault(iso, set()).add(l3)

    wd = wikidata_continents()
    continents = {c: [] for c in CONTINENTS}
    unresolved = []
    for iso, l3s in sorted(country_l3.items()):
        conts = wd.get(iso, set())
        if iso in TIE_BREAK:
            cont = TIE_BREAK[iso]
        elif len(conts) == 1:
            cont = next(iter(conts))
        else:
            # Wikidata に無い／決められない → TDWG の大陸の多数決
            votes: dict[str, int] = {}
            for l3 in l3s:
                k = TDWG_L1.get(l3_to_l1.get(l3, ""))
                if k:
                    votes[k] = votes.get(k, 0) + 1
            cont = max(votes, key=votes.get) if votes else None
            if cont is None:
                unresolved.append(iso)
                continue
        continents[cont].append({"iso": iso, "l3": sorted(l3s)})

    out = {
        "sources": [
            {"source": TDWG_SOURCE, "source_url": TDWG_SOURCE_URL, "license": "CC BY 4.0",
             "license_url": "https://creativecommons.org/licenses/by/4.0/", "retrieved": today()},
            {"source": "Wikidata（国 → 大陸）", "source_url": "https://www.wikidata.org/", "license": "CC0 1.0", "retrieved": today()},
        ],
        "continents": [{"code": c, "countries": continents[c]} for c in CONTINENTS],
    }
    save_json(DATA_DIR / "places.json", out)
    log("州ごとの国の数: " + ", ".join(f"{c} {len(continents[c])}" for c in CONTINENTS))
    if unresolved:
        log("州を決められなかったコード（除外）: " + " ".join(unresolved))


if __name__ == "__main__":
    main()
