"""DESIGN.md: text roles reach WCAG AA (4.5:1) on the page and panel surfaces."""

import colorsys
import re
from pathlib import Path

import pytest

WEB = Path(__file__).parents[2] / "web"
THEME = WEB / "theme.css"
# View → Theme (D-303): Solum is :root; the others change it
THEMES = [":root", ':root[data-theme="dark"]', ':root[data-theme="light"]']


def block(selector: str) -> str:
    """The declarations of one rule in theme.css (`:root`, `.print`)."""
    found = re.search(
        rf"^{re.escape(selector)}\s*(?:,[^{{]*)?\{{(.*?)^\}}", THEME.read_text(), re.S | re.M
    )
    assert found, f"no {selector} rule in theme.css"
    return found[1]


def tokens(selector: str = ":root") -> dict[str, str]:
    """Hex value of every token in :root (or, with `selector`, :root as that rule changes
    it), with var() references resolved."""
    raw = dict(re.findall(r"--([\w-]+):\s*([^;]+);", block(":root")))
    if selector != ":root":
        raw |= dict(re.findall(r"--([\w-]+):\s*([^;]+);", block(selector)))
    resolved: dict[str, str] = {}

    def value(name: str) -> str:
        v = raw[name].strip()
        ref = re.fullmatch(r"var\(--([\w-]+)\)", v)
        return value(ref[1]) if ref else v

    for name in raw:
        resolved[name] = value(name)
    return resolved


def luminance(hex_colour: str) -> float:
    channels = [int(hex_colour.lstrip("#")[i : i + 2], 16) / 255 for i in (0, 2, 4)]
    linear = [c / 12.92 if c <= 0.03928 else ((c + 0.055) / 1.055) ** 2.4 for c in channels]
    return 0.2126 * linear[0] + 0.7152 * linear[1] + 0.0722 * linear[2]


def contrast(a: str, b: str) -> float:
    hi, lo = sorted((luminance(a), luminance(b)), reverse=True)
    return (hi + 0.05) / (lo + 0.05)


def test_contrast_formula() -> None:
    assert contrast("#FFFFFF", "#000000") == pytest.approx(21.0)


@pytest.mark.parametrize(
    "text",
    [
        "text",
        "text-2",
        "text-3",
        "accent-hi",
        "error",
        "warning",
        "picked",
        "sch-impedance",
        "sch-type",
        "sch-supply",
    ],
)
@pytest.mark.parametrize("surface", ["surface-0", "surface-1"])
@pytest.mark.parametrize("theme", THEMES)
def test_text_roles_reach_aa(text: str, surface: str, theme: str) -> None:
    t = tokens(theme)
    assert contrast(t[text], t[surface]) >= 4.5, f"--{text} on --{surface}"


def hue(hex_colour: str) -> float:
    r, g, b = (int(hex_colour.lstrip("#")[i : i + 2], 16) / 255 for i in (0, 2, 4))
    return colorsys.rgb_to_hsv(r, g, b)[0] * 360


@pytest.mark.parametrize("theme", THEMES)
def test_picked_reads_neither_as_an_error_nor_as_the_highlight(theme: str) -> None:
    """D-127: a stage picked has its own colour, at least 15 degrees of hue from the brick
    error and the brass highlight."""
    t = tokens(theme)
    for other in ("error", "accent-hi"):
        apart = abs(hue(t["picked"]) - hue(t[other]))
        assert min(apart, 360 - apart) >= 15, f"--picked too close to --{other}"


@pytest.mark.parametrize("theme", THEMES)
def test_a_supply_name_reads_apart_from_an_error(theme: str) -> None:
    """D-225: a supply's name is rose, at least 15 degrees of hue from the brick error and
    the copper of a picked stage, so power never reads as a problem."""
    t = tokens(theme)
    for other in ("error", "picked"):
        apart = abs(hue(t["sch-supply"]) - hue(t[other]))
        assert min(apart, 360 - apart) >= 15, f"--sch-supply too close to --{other}"


@pytest.mark.parametrize("theme", THEMES)
def test_schematic_readings_each_have_their_own_hue(theme: str) -> None:
    """D-147: DC voltages, impedances and capacitor types read apart at a glance: at least
    30 degrees of hue between each pair."""
    t = tokens(theme)
    roles = ["sch-dc", "sch-impedance", "sch-type"]
    for i, a in enumerate(roles):
        for b in roles[i + 1 :]:
            apart = abs(hue(t[a]) - hue(t[b]))
            assert min(apart, 360 - apart) >= 30, f"--{a} too close to --{b}"


@pytest.mark.parametrize("text", ["text", "text-2", "text-3", "sch-line", "sch-supply", "sch-type"])
def test_print_colours_read_on_paper(text: str) -> None:
    """D-205: a printed schematic's text and lines on white (brass, for capacitor types,
    is a large-text colour: 3:1)."""
    t = tokens(".print")
    need = 3.0 if text == "sch-type" else 4.5
    assert contrast(t[text], t["surface-0"]) >= need


def test_the_early_script_reads_the_themes_key_and_names() -> None:
    """theme-start.js can't import theme.js (it runs before modules): same key, same ids."""
    start = (WEB / "theme-start.js").read_text()
    assert (
        '"solum.theme"' in start and 'THEME_KEY = "solum.theme"' in (WEB / "theme.js").read_text()
    )
    assert 'id === "dark" || id === "light"' in start
