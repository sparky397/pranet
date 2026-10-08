# 出典一覧

pranet が使うデータ元と、確認した日付・内容。詳しい条件は [LICENSE-DATA.md](LICENSE-DATA.md)。

| データ元 | 取っているもの | 取得先 | 版 | ライセンス | 確認日 |
|---|---|---|---|---|---|
| World Flora Online Plant List | 学名、固定番号（wfo-…）、科、異名、IPNI 対応表 | https://zenodo.org/records/20782718 | 2026年6月版 | CC0 1.0 | 2026-10-08 |
| World Checklist of Useful Plant Species（Diazgranados ほか 2020、RBG Kew） | 食用かどうか（用途コード HF）、作物野生近縁種か | https://doi.org/10.5063/F1CV4G34 （PDF） | 2020 | CC BY 4.0（メタデータ XML の intellectualRights） | 2026-10-08 |
| World Checklist of Vascular Plants（RBG Kew） | 分布（自生／導入、TDWG level 3）、生活形、気候帯 | https://sftp.kew.org/pub/data-repositories/WCVP/ | 2026-06-04 抽出（version 16） | CC BY 3.0（同梱 README）。GBIF 登録では CC BY 4.0 | 2026-10-08 |
| Wikidata | 各国語の名前（P1843、ラベル、別名）、WFO ID（P7715）、Wikipedia 記事名、写真候補（P18）、iNaturalist ID（P3151） | https://www.wikidata.org/ | 取得時点 | CC0 1.0 | 2026-10-08 |
| Wikipedia | 冒頭要約と版 ID（日本語、無ければ英語） | https://ja.wikipedia.org/ ほか | 版 ID を記録 | CC BY-SA 4.0 | 2026-10-08（利用規約 第7条） |
| Wikimedia Commons | 写真（ファイルごとに extmetadata で確認） | https://commons.wikimedia.org/ | ファイルごと | CC0 / CC BY / CC BY-SA / パブリックドメイン のみ | 2026-10-08（Commons:Licensing） |
| iNaturalist | 写真（license_code が cc0 / cc-by のもののみ） | https://api.inaturalist.org/ | 写真ごと | CC0 / CC BY 4.0 | 2026-10-08 |
| TDWG World Geographical Scheme for Recording Plant Distributions（WGSRPD）レベル 4 | 国（ISO コード）→ 地区の対応（場所画面の「国」） | https://github.com/tdwg/wgsrpd （tblLevel4.txt） | 第 2 版 | CC BY 4.0（TDWG のサイト表記） | 2026-10-08 |
| Wikidata（国 → 大陸） | 国を 6 つの州に振り分ける | https://query.wikidata.org/ | 取得時点 | CC0 1.0 | 2026-10-08 |

## 使っていない・保留のデータ元

| データ元 | 理由 |
|---|---|
| World Flora Online の Web API | この PC から SSL 証明書エラーで到達できない。Zenodo の公開版で代替 |
| GBIF（出現記録） | 栽培・逸出・誤同定が混ざるため、分布は WCVP を主にする。後の地域パックで補助的に検討 |
| 機械翻訳 | 「AI に植物の事実を書かせない」原則に抵触しうるため使わない |

## 分かっていること・分かっていないこと

- WCUP は「食用かどうか」しか分からない。「どの部分を、どう食べるか」の出典は未定（設計図 13 章）。
- 特徴（絞り込み用）の出典は未定。WCVP の生活形・気候帯の記述を `traits_raw` として保持している。
