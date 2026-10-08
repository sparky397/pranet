# データと写真のライセンス

pranet のソースコードは MIT ライセンスですが、**データと写真は項目ごとにライセンスが異なります**。
各項目には必ず `source`（出典）と `license`（ライセンス）が付いています。付いていないデータは取り込みません。

| データ元 | 使っている内容 | ライセンス | 条件 |
|---|---|---|---|
| World Flora Online Plant List | 学名、固定番号、科、異名 | CC0 1.0 | 条件なし |
| Wikidata | 各国語の名前、対応表 | CC0 1.0 | 条件なし |
| World Checklist of Useful Plant Species（Kew） | 食用かどうか | CC BY 4.0 | 出典を表示する |
| World Checklist of Vascular Plants（Kew） | 分布 | CC BY 4.0 | 出典を表示する |
| Wikipedia | 説明文（冒頭要約） | CC BY-SA 4.0 | 出典と版を表示し、同じ条件で公開する |
| Wikimedia Commons / iNaturalist | 写真 | 写真ごと（CC0、CC BY、CC BY-SA のいずれか） | 作者名・ライセンス・改変（縮小）の旨を表示する |

写真の作者一覧は [ATTRIBUTION.md](ATTRIBUTION.md) にあります（スクリプトが自動生成します）。

アプリの一覧（小さい写真の格子）では帰属表示を省略し、大きい写真の一覧と詳細ページで、作者名・ライセンス・元ページ・改変（縮小）の旨を表示しています。共有カードの画像にも同じ内容を焼き込みます。

パック（`data/packs/*.json`）全体としては、含まれる項目のうち最も条件の強いライセンス（Wikipedia の説明文を含む場合は CC BY-SA 4.0）に従って再配布してください。
