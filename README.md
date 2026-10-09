# pranet

世界中の誰でも無料で使える、正しい方法で作られた植物図鑑。
まず世界の食用植物から始め、最終的には世界のすべての植物を載せることを目指します。

- **使う**: https://sparky397.github.io/pranet/
- 間違いの報告: [Issues](https://github.com/sparky397/pranet/issues)（出典付きの訂正は [docs/訂正の提案のしかた.md](docs/訂正の提案のしかた.md) の形で取り込みます）

- 設計：[pranet_設計図.md](pranet_設計図.md)
- 引き継ぎ：[docs/引き継ぎの手引き.md](docs/引き継ぎの手引き.md)（誰でも続けられるように）
- 広め方：[docs/世界一への道筋.md](docs/世界一への道筋.md)
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
