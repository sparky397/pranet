# pranet

世界中の誰でも無料で使える、正しい方法で作られた植物図鑑。
まず世界の食用植物から始め、最終的には世界のすべての植物を載せることを目指します。

- 設計：[pranet_設計図.md](pranet_設計図.md)
- コードのライセンス：MIT（[LICENSE](LICENSE)）
- データと写真のライセンス：項目ごとに異なります（[docs/LICENSE-DATA.md](docs/LICENSE-DATA.md)、[docs/ATTRIBUTION.md](docs/ATTRIBUTION.md)）

## フォルダ

| フォルダ | 中身 |
|---|---|
| `app/` | 図鑑アプリ本体（ブラウザで動く） |
| `data/packs/` | パックごとのデータ（JSON） |
| `data/photos/` | 小さい写真 |
| `scripts/` | データを集める Python スクリプト |
| `i18n/` | 画面の文字（言語ごと） |
| `docs/` | 出典一覧、ライセンス、帳簿 |
| `ai/` | ローカルAI（後から追加） |

## データの作り方（開発者向け）

```bash
python3 -m venv .venv
.venv/bin/pip install -r scripts/requirements.txt
.venv/bin/python scripts/build_all.py
```

詳しくは [scripts/README.md](scripts/README.md) を見てください。

## 免責

同定や利用は自己責任でお願いします。この図鑑だけを根拠に野生の植物を食べないでください。
