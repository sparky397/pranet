# データ収集スクリプト

PC で実行し、`data/packs/` と `data/photos/`、`docs/ATTRIBUTION.md` を作ります。

## 必要なもの

- Python 3.12 以上と `requests`、`Pillow`（`scripts/requirements.txt`）
- `pdftotext`（poppler-utils）。WCUP が PDF でしか公開されていないため
- 初回は約 230 MB のダウンロード（WFO 122 MB、WCVP 88 MB、WCUP の PDF 11 MB）

## 実行

```bash
python3 scripts/build_all.py
```

1 種だけ試すとき：

```bash
python3 scripts/build_all.py "Oryza sativa"
```

## 流れ

| 順 | スクリプト | 取るもの | 出典 | ライセンス |
|---|---|---|---|---|
| 1 | `fetch_wfo.py` | 学名、固定番号、科、異名 | World Flora Online（Zenodo 公開版） | CC0 1.0 |
| 2 | `fetch_wcup.py` | 食用かどうか | World Checklist of Useful Plant Species 2020（PDF） | CC BY 4.0 |
| 3 | `fetch_wikidata.py` | 各国語名、Wikipedia 記事名、写真候補 | Wikidata | CC0 1.0 |
| 4 | `fetch_wikipedia.py` | 冒頭要約と版 ID（日本語、無ければ英語） | Wikipedia | CC BY-SA 4.0 |
| 5 | `fetch_photo.py` | 写真 1 枚（ライセンス確認・縮小） | Wikimedia Commons / iNaturalist | 写真ごと |
| 6 | `fetch_wcvp.py` | 分布、生活形、気候帯 | World Checklist of Vascular Plants | CC BY 3.0 |
| 7 | `validate.py` | 出典・ライセンスの検査 | | |
| 8 | `build_pack.py` | パックと作者一覧の生成 | | |

## 分かっている限界

- WCUP の PDF からは 40,292 種のうち 40,224 種（食用 7,039 種のうち 7,001 種）を読み取れています（2026-10-08 時点）。残りは IPNI 番号を持たない藻類などと推定しており、第 2 段階で確認します。
- WCUP には「どの部分を食べるか」が無いので `edible.parts` は作っていません。
- 特徴（絞り込み用）は未作成です。WCVP の生活形・気候帯の記述を `traits_raw` に保持しています。

## 中間ファイル

`scripts/cache/work/<学名>/` に段階ごとの JSON を置きます。`scripts/cache/` は git 管理外です。
取得した API の応答は `scripts/cache/http/` に保存され、再実行では再取得しません。
取り直したいときは該当のファイルを消してから実行してください。

## 種の追加

`species_list.csv` に学名を足します。WFO で Accepted の種が 1 件に定まらない場合は取り込まれず、理由が表示されます。
人が確認したうえで番号を指定したいときは `wfo_id` 列を足してください。
