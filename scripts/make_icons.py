"""ホーム画面用のアイコンを描く（外部の画像は使わない）。

出力：app/icons/icon-192.png, icon-512.png, icon-512-maskable.png
図柄：深緑の角丸の中に、明るい緑の葉（楕円を傾けたもの）と葉脈。
"""

from __future__ import annotations

from pathlib import Path

from PIL import Image, ImageDraw

OUT = Path(__file__).resolve().parent.parent / "app" / "icons"
BG = (47, 107, 58)        # --accent
LEAF = (229, 239, 230)    # --accent-soft
VEIN = (47, 107, 58)


def draw(size: int, maskable: bool) -> Image.Image:
    s = size * 4  # 大きく描いて縮小し、縁を滑らかにする
    im = Image.new("RGBA", (s, s), (0, 0, 0, 0))
    d = ImageDraw.Draw(im)
    radius = 0 if maskable else s // 5
    d.rounded_rectangle([0, 0, s - 1, s - 1], radius=radius, fill=BG)
    # 葉：傾けた楕円を別の画像に描いて回転して貼る
    pad = s * (0.26 if maskable else 0.20)
    leaf = Image.new("RGBA", (s, s), (0, 0, 0, 0))
    ld = ImageDraw.Draw(leaf)
    ld.ellipse([s / 2 - s * 0.19, pad, s / 2 + s * 0.19, s - pad], fill=LEAF)
    ld.line([(s / 2, pad + s * 0.06), (s / 2, s - pad - s * 0.04)], fill=VEIN, width=max(2, s // 60))
    for i in range(1, 5):
        y = pad + s * 0.12 + i * (s - 2 * pad - s * 0.2) / 5
        ld.line([(s / 2, y), (s / 2 - s * 0.11, y - s * 0.07)], fill=VEIN, width=max(2, s // 80))
        ld.line([(s / 2, y), (s / 2 + s * 0.11, y - s * 0.07)], fill=VEIN, width=max(2, s // 80))
    leaf = leaf.rotate(-28, resample=Image.BICUBIC, center=(s / 2, s / 2))
    im.alpha_composite(leaf)
    return im.resize((size, size), Image.LANCZOS)


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    draw(192, False).save(OUT / "icon-192.png")
    draw(512, False).save(OUT / "icon-512.png")
    draw(512, True).save(OUT / "icon-512-maskable.png")
    print("アイコンを書き出しました:", OUT)


if __name__ == "__main__":
    main()
