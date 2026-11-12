"""Convert the <text> wordmark in a brand SVG to outlined paths (DESIGN.md, Phase 2).

Shaping by HarfBuzz (kerning as a browser would), outlines from fontTools. Letter-spacing
is added after every glyph, the last included, as browsers do, so text-anchor="middle"
lands where the browser put it. Everything else in the file is copied unchanged.

usage (in a scratch venv with fonttools + uharfbuzz):
    outline_svg_text.py <in.svg> <out.svg> <font.ttf>
"""

import re
import sys
from pathlib import Path

import uharfbuzz as hb
from fontTools.pens.svgPathPen import SVGPathPen
from fontTools.pens.transformPen import TransformPen
from fontTools.ttLib import TTFont

TEXT = re.compile(r"<text\b([^>]*)>([^<]*)</text>")


def attr(attrs: str, name: str, default: str | None = None) -> str:
    m = re.search(rf'\b{name}="([^"]*)"', attrs)
    if m is None:
        if default is None:
            raise SystemExit(f"text element has no {name}")
        return default
    return m[1]


def outline(attrs: str, text: str, font_path: str) -> str:
    font = TTFont(font_path)
    upem = font["head"].unitsPerEm
    glyphs = font.getGlyphSet()
    order = font.getGlyphOrder()
    blob = hb.Blob.from_file_path(font_path)
    hbfont = hb.Font(hb.Face(blob))
    buf = hb.Buffer()
    buf.add_str(text)
    buf.guess_segment_properties()
    hb.shape(hbfont, buf, {"kern": True, "liga": False})

    x0, y0 = float(attr(attrs, "x")), float(attr(attrs, "y"))
    size = float(attr(attrs, "font-size"))
    spacing = float(attr(attrs, "letter-spacing", "0"))
    anchor = attr(attrs, "text-anchor", "start")
    scale = size / upem

    advances = [p.x_advance * scale + spacing for p in buf.glyph_positions]
    width = sum(advances)
    start = x0 - {"start": 0.0, "middle": width / 2, "end": width}[anchor]

    pen = SVGPathPen(glyphs, ntos=lambda v: f"{v:.2f}".rstrip("0").rstrip("."))
    x = start
    for info, pos, adv in zip(buf.glyph_infos, buf.glyph_positions, advances, strict=True):
        name = order[info.codepoint]
        ox, oy = x + pos.x_offset * scale, y0 - pos.y_offset * scale
        glyphs[name].draw(TransformPen(pen, (scale, 0, 0, -scale, ox, oy)))
        x += adv
    keep = " ".join(f'{k}="{attr(attrs, k)}"' for k in ("fill", "opacity") if f"{k}=" in attrs)
    return f'<path {keep} d="{pen.getCommands()}"/>'


def main() -> None:
    src, dst, font_path = sys.argv[1:4]
    svg = Path(src).read_text(encoding="utf-8")
    out, n = TEXT.subn(lambda m: outline(m[1], m[2], font_path), svg)
    if n != 1:
        raise SystemExit(f"expected one <text> element, found {n}")
    Path(dst).write_text(out, encoding="utf-8")


if __name__ == "__main__":
    main()
