"""The Mac app's icon from the brand's favicon (D-321): `favicon-outlined.svg` drawn as it
is, on a clear square with the margin macOS icons keep, at each size an `.iconset` needs.
Nothing is redrawn (DESIGN.md). Usage: python scripts/mac_icon.py OUT.iconset"""

import io
import sys
from pathlib import Path

import cairosvg
from PIL import Image

SVG = Path(__file__).resolve().parents[1] / "web" / "assets" / "brand" / "favicon-outlined.svg"
MARGIN = 0.08  # of the side, each side: about what Apple's icon grid leaves


def icon(side: int) -> Image.Image:
    inner = round(side * (1 - 2 * MARGIN))
    png = cairosvg.svg2png(url=str(SVG), output_width=inner, output_height=inner)
    canvas = Image.new("RGBA", (side, side), (0, 0, 0, 0))
    canvas.alpha_composite(Image.open(io.BytesIO(png)).convert("RGBA"), ((side - inner) // 2,) * 2)
    return canvas


def main(out: Path) -> None:
    out.mkdir(parents=True, exist_ok=True)
    for points in (16, 32, 128, 256, 512):
        icon(points).save(out / f"icon_{points}x{points}.png")
        icon(points * 2).save(out / f"icon_{points}x{points}@2x.png")


if __name__ == "__main__":
    main(Path(sys.argv[1]))
