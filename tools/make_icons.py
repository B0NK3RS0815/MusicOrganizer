"""Erzeugt App-Icons (.ico für Windows, .icns für macOS, PNG) aus mog_icon.svg.

Benötigt: pip install cairosvg pillow
"""
import io
from pathlib import Path

import cairosvg
from PIL import Image

RES = Path(__file__).resolve().parent.parent / "mog" / "resources"
svg = (RES / "mog_icon.svg").read_bytes()


def render(size):
    png = cairosvg.svg2png(bytestring=svg, output_width=size, output_height=size)
    return Image.open(io.BytesIO(png)).convert("RGBA")


big = render(1024)
big.save(RES / "mog_icon_1024.png")
render(256).save(RES / "mog_icon_256.png")
# Windows: mehrere Größen in einer .ico
render(256).save(RES / "mog.ico", sizes=[(16, 16), (24, 24), (32, 32), (48, 48), (64, 64), (128, 128), (256, 256)])
# macOS: .icns (Pillow erzeugt alle nötigen Auflösungen aus dem 1024er-Bild)
big.save(RES / "mog.icns")
print("Icons geschrieben nach", RES)
