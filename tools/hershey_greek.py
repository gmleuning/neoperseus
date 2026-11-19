"""Make the web font for the landing-page title from Hershey Greek Simplex.

The converted Hershey TTF puts the Greek glyphs on the Latin keys in alphabetical
order (A=alpha ... H=theta ... R=sigma ... X=omega). This maps them to the real Greek
code points as well, so pages can contain proper Greek text, and writes a small font:

    python tools/hershey_greek.py "I:/My Drive/Archive/Fonts/HersheyFonts/ttf/GREEKS.ttf"
"""
import sys
from pathlib import Path

from fontTools.ttLib import TTFont

UPPER = "ΑΒΓΔΕΖΗΘΙΚΛΜΝΞΟΠΡΣΤΥΦΧΨΩ"
LOWER = "αβγδεζηθικλμνξοπρστυφχψω"
KEYS = "ABCDEFGHIJKLMNOPQRSTUVWX"


def main(src, out=Path(__file__).resolve().parent.parent / "assets" / "fonts" / "HersheyGreekSimplex.ttf"):
    font = TTFont(src)
    cmap = font.getBestCmap()
    extra = {}
    for g, k in zip(UPPER, KEYS):
        extra[ord(g)] = cmap[ord(k)]
    for g, k in zip(LOWER, KEYS.lower()):
        extra[ord(g)] = cmap[ord(k)]
    extra[ord("ς")] = cmap[ord("r")]          # no final sigma in Hershey: use σ
    for table in font["cmap"].tables:
        if table.isUnicode():
            table.cmap.update(extra)
    font.save(out)
    print(f"wrote {out}")


if __name__ == "__main__":
    main(sys.argv[1])
