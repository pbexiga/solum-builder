"""The user guide's pages in the app (solum/manual.py, D-290)."""

from pathlib import Path

import pytest

from solum.manual import (
    MAX_RESULTS,
    ManualError,
    anchor_of,
    load_manual,
    page_html,
    render_page,
)

GUIDE = Path(__file__).parents[2] / "docs" / "guide"

PAGE = """# Drawing a circuit

Place parts from the palette. See [probing](probing.md#the-scope) and the [start](README.md).

## Wires

Drag from a pin. A wire `snaps` to the grid.

## Wires

Again, with a [link out](https://example.com/x.md).

| Key | Does |
|---|---|
| W | wire |

<b>not html</b>
"""


def test_anchor_is_the_headings_words_numbered_when_taken() -> None:
    taken: set[str] = set()
    assert anchor_of("RC corner frequency", taken) == "rc-corner-frequency"
    assert anchor_of("RC corner: frequency!", taken) == "rc-corner-frequency-2"
    assert anchor_of("µ", taken) == "section"
    assert taken == {"rc-corner-frequency", "rc-corner-frequency-2", "section"}


def test_render_gives_ids_page_links_and_sections() -> None:
    page = render_page("drawing", PAGE)
    assert page.title == "Drawing a circuit"
    assert '<h1 id="drawing-a-circuit">' in page.html
    assert '<h2 id="wires">' in page.html and '<h2 id="wires-2">' in page.html
    # links to other pages follow the app's addresses; README is the first page
    assert '<a href="./probing#the-scope">probing</a>' in page.html
    assert '<a href="./">start</a>' in page.html
    # a link out opens in a new tab and is left as written
    assert '<a href="https://example.com/x.md" target="_blank" rel="noopener">' in page.html
    assert "<table>" in page.html and "<b>" not in page.html  # tables on, raw HTML off
    assert [(s.heading, s.anchor, s.level) for s in page.sections] == [
        ("Drawing a circuit", "", 1),  # the title's results link to the top of the page
        ("Wires", "wires", 2),
        ("Wires", "wires-2", 2),
    ]
    assert page.sections[1].text == "Drag from a pin. A wire snaps to the grid."


def test_a_page_with_no_heading_is_named_after_its_file() -> None:
    page = render_page("notes", "Just a line.")
    assert page.title == "notes"
    assert [(s.heading, s.text) for s in page.sections] == [("", "Just a line.")]


@pytest.fixture
def guide(tmp_path: Path) -> Path:
    (tmp_path / "README.md").write_text("# Guide\n\n- [B](beta.md)\n- [A](alpha.md#x)\n")
    (tmp_path / "alpha.md").write_text("# Alpha\n\n## Corner\n\nThe RC corner is 720 Hz.\n")
    (tmp_path / "beta.md").write_text("# Beta\n\nA corner case, about RC parts.\n")
    (tmp_path / "zeta.md").write_text("# Zeta\n\nNot linked from the first page.\n")
    return tmp_path


def test_pages_follow_the_first_pages_links_then_the_rest(guide: Path) -> None:
    manual = load_manual(guide)
    assert [(p.slug, p.title) for p in manual.pages] == [
        ("", "Guide"), ("beta", "Beta"), ("alpha", "Alpha"), ("zeta", "Zeta"),
    ]  # fmt: skip
    assert manual.get("alpha").title == "Alpha"
    with pytest.raises(ManualError, match="no page called 'nope'"):
        manual.get("nope")
    assert load_manual(guide / "missing").pages == []


def test_search_finds_sections_with_every_word_headings_first(guide: Path) -> None:
    manual = load_manual(guide)
    found = manual.search("CORNER rc")
    assert [(r.slug, r.heading, r.anchor) for r in found] == [
        ("beta", "Beta", ""),
        ("alpha", "Corner", "corner"),
    ]  # neither heading has both words: page order
    assert [(r.slug, r.heading) for r in manual.search("corner")] == [
        ("alpha", "Corner"),  # in the heading: first
        ("beta", "Beta"),
    ]
    assert found[1].snippet == "The RC corner is 720 Hz."
    assert manual.search("") == [] and manual.search("germanium corner") == []


def test_a_snippet_is_cut_around_the_word_found(tmp_path: Path) -> None:
    words = " ".join(f"word{i}" for i in range(80))
    (tmp_path / "README.md").write_text(f"# Long\n\n{words} needle {words}\n")
    (snippet,) = [r.snippet for r in load_manual(tmp_path).search("needle")]
    assert snippet.startswith("…") and snippet.endswith("…") and "needle" in snippet
    assert len(snippet) <= 170
    many = "\n\n".join(f"## Part {i}\n\nsame" for i in range(MAX_RESULTS + 5))
    (tmp_path / "README.md").write_text(f"# Many\n\n{many}\n")
    assert len(load_manual(tmp_path).search("same")) == MAX_RESULTS


def test_the_page_lists_the_pages_and_its_own_headings(guide: Path) -> None:
    manual = load_manual(guide)
    html = page_html(manual, manual.get("alpha"))
    assert "<title>Alpha · Solum Builder guide</title>" in html
    assert '<a href="./alpha" aria-current="page">Alpha</a>' in html
    assert '<a class="part" href="#corner">Corner</a>' in html
    assert '<a href="./beta">Beta</a>' in html and '<a href="./">Guide</a>' in html
    assert 'href="../theme.css"' in html and 'src="../manual.js"' in html


def test_the_page_list_is_grouped_by_the_first_pages_sections(tmp_path: Path) -> None:
    """D-301: each `##` section of the first page heads a group of the pages it links; pages
    linked before any section, and pages it doesn't link, stand alone; a page linked twice
    stays in its first group. The first page's own sections aren't listed under it again."""
    (tmp_path / "README.md").write_text(
        "# Guide\n\n- [I](intro.md)\n\n## Designing\n\n- [B](beta.md)\n- [I](intro.md)\n"
        "\n## Empty\n\nNo links.\n\n## Advanced & more\n\n- [A](alpha.md#x)\n"
    )
    for slug in ("intro", "beta", "zeta"):
        (tmp_path / f"{slug}.md").write_text(f"# {slug.title()}\n")
    (tmp_path / "alpha.md").write_text("# Alpha\n\n## Corner\n\nThe RC corner is 720 Hz.\n")
    manual = load_manual(tmp_path)
    assert manual.groups == (
        ("", ("intro",)), ("Designing", ("beta",)), ("Advanced & more", ("alpha",)),
    )  # fmt: skip
    assert [p.slug for p in manual.pages] == ["", "intro", "beta", "alpha", "zeta"]
    html = page_html(manual, manual.get("alpha"))
    assert (
        '<div class="manual-group"><p class="manual-group-title">Advanced &amp; more</p>'
        '<a href="./alpha" aria-current="page">Alpha</a><a class="part" href="#corner">Corner</a>'
        "</div>"
    ) in html
    assert '<a href="./">Guide</a><a href="./intro">Intro</a><div class="manual-group">' in html
    assert '</div><a href="./zeta">Zeta</a></div>' in html  # unlinked: last, on its own
    home = page_html(manual, manual.get(""))
    assert 'aria-current="page">Guide</a><a href="./intro">' in home
    assert 'href="#designing"' not in home


def test_the_real_guide_loads_with_formulas_and_every_link_lands() -> None:
    """The shipped pages: the first page links each one, and every link between pages
    names a page (and a heading) that exists."""
    import re

    manual = load_manual(GUIDE)
    slugs = {p.slug for p in manual.pages}
    assert {"", "formulas", "germanium"} <= slugs
    anchors = {p.slug: {s.anchor for s in p.sections} for p in manual.pages}
    for page in manual.pages:
        for slug, anchor in re.findall(r'<a href="\./([a-z0-9_-]*)(?:#([^"]*))?"', page.html):
            assert slug in slugs, f"{page.slug or 'README'} links to a missing page: {slug}"
            assert not anchor or anchor in anchors[slug], f"{page.slug}: no heading #{anchor}"
    (corner,) = [r for r in manual.search("corner frequency") if r.slug == "formulas"][:1]
    assert corner.heading == "RC corner frequency" and corner.anchor == "rc-corner-frequency"


def test_every_picture_the_guide_names_is_there() -> None:
    """Pictures are `img/<name>.png`, made by scripts/guide_shots.py; a page naming one
    that isn't in docs/guide/img would show a broken image, in the app and on GitHub."""
    import re

    named = {m for f in GUIDE.glob("*.md") for m in re.findall(r"\]\((img/[^)]+)\)", f.read_text())}
    assert named, "the guide names no pictures"
    missing = sorted(n for n in named if not (GUIDE / n).is_file())
    assert not missing, f"run scripts/guide_shots.py: missing {missing}"


def test_whats_included_lists_every_starter_and_core_block() -> None:
    """docs/guide/whats-included.md has a row for each shipped starter and core block, by
    the name the app shows; a new one fails here until its line is written."""
    import json

    page = (GUIDE / "whats-included.md").read_text()
    library = GUIDE.parents[1] / "library"
    files = sorted((library / "starters").glob("*.json")) + sorted(
        (library / "blocks").glob("*.json")
    )
    names = [json.loads(f.read_text())["name"] for f in files]
    assert len(names) > 20
    missing = [n for n in names if f"| {n} |" not in page]
    assert not missing, f"add a line to whats-included.md for: {missing}"
