"""The user guide as pages in the app (9e, D-290): `docs/guide/*.md` rendered to HTML by
markdown-it-py, each at its own address (`/manual/<page>`), with the list of pages, the
page's own headings, and a search over every section. The Markdown files stay as they are,
so they read the same on GitHub: `README.md` is the first page, and the pages it links to
follow in that order.
"""

import re
from dataclasses import dataclass
from html import escape
from pathlib import Path

from markdown_it import MarkdownIt
from markdown_it.token import Token

INDEX = "README"  # the first page's file; its address is `/manual/`
MAX_RESULTS = 30
SNIPPET = 160  # characters of a section shown under a search result

_MD = MarkdownIt("commonmark", {"html": False}).enable("table")
_EXTERNAL = re.compile(r"^[a-z][a-z0-9+.-]*:", re.IGNORECASE)
_PAGE_LINK = re.compile(r"^(?:\./)?([A-Za-z0-9_-]+)\.md(#.*)?$")


class ManualError(ValueError):
    """Plain-English problem with the guide's pages."""


@dataclass(frozen=True)
class Section:
    """A heading and the text under it, up to the next heading: what search looks through."""

    heading: str
    anchor: str  # "" for the page's own title
    level: int
    text: str


@dataclass(frozen=True)
class Page:
    slug: str  # the address after `/manual/`; "" for the first page
    title: str
    html: str  # the rendered body
    sections: tuple[Section, ...]


@dataclass(frozen=True)
class Result:
    """One search result: a section of a page."""

    slug: str
    title: str
    heading: str
    anchor: str
    snippet: str


def anchor_of(heading: str, taken: set[str]) -> str:
    """A heading's id: its words in lower case joined by hyphens, numbered when the page
    already has one the same (`taken` is added to)."""
    base = re.sub(r"[^a-z0-9]+", "-", heading.lower()).strip("-") or "section"
    anchor, n = base, 2
    while anchor in taken:
        anchor, n = f"{base}-{n}", n + 1
    taken.add(anchor)
    return anchor


def _plain(token: Token) -> str:
    """An inline token's words, without the Markdown marks."""
    parts = [
        " " if c.type in ("softbreak", "hardbreak") else c.content
        for c in token.children or []
        if c.type in ("text", "code_inline", "softbreak", "hardbreak")
    ]
    return "".join(parts)


def _link(href: str) -> str:
    """A link to another page of the guide (`other.md#part`) as its address in the app."""
    found = _PAGE_LINK.match(href)
    if not found:
        return href
    slug = "" if found.group(1) == INDEX else found.group(1)
    return f"./{slug}{found.group(2) or ''}"


def _fix_links(token: Token) -> None:
    """Links between pages follow the app's addresses; links out open in a new tab (the
    guide may be showing inside the app's window)."""
    for child in token.children or []:
        if child.type != "link_open":
            continue
        href = str(child.attrGet("href") or "")
        if _EXTERNAL.match(href):
            child.attrSet("target", "_blank")
            child.attrSet("rel", "noopener")
        else:
            child.attrSet("href", _link(href))


def render_page(slug: str, text: str) -> Page:
    """A Markdown page as HTML, its headings given ids, with its sections for search. The
    title is its first heading (the file's name if it has none)."""
    tokens = _MD.parse(text)
    taken: set[str] = set()
    sections: list[Section] = []
    words: list[str] = []
    heading, anchor, level = "", "", 1
    title = ""
    for i, token in enumerate(tokens):
        if token.type == "heading_open":
            if heading or words:
                sections.append(Section(heading, anchor, level, " ".join(words)))
            heading, level, words = _plain(tokens[i + 1]), int(token.tag[1]), []
            anchor = anchor_of(heading, taken)
            token.attrSet("id", anchor)
            if not title:
                title, anchor = heading, ""  # the page's title: its results link to the top
        elif token.type == "inline":
            _fix_links(token)
            if i == 0 or tokens[i - 1].type != "heading_open":
                words.append(_plain(token))
        elif token.type in ("fence", "code_block"):
            words.append(token.content.strip())
    if heading or words:
        sections.append(Section(heading, anchor, level, " ".join(words)))
    html = str(_MD.renderer.render(tokens, _MD.options, {}))
    return Page(slug, title or slug or "Guide", html, tuple(sections))


Group = tuple[str, tuple[str, ...]]  # a section of the first page, and the pages it links


def _groups(text: str, pages: set[str]) -> tuple[Group, ...]:
    """The first page's `##` sections, each with the pages of `pages` it links in order
    (the guide's order and its page list's groups, D-301). Links before any section form an
    untitled group; a page linked twice stays in its first; a section with none is left out."""
    groups: list[tuple[str, list[str]]] = [("", [])]
    seen: set[str] = set()
    for line in text.splitlines():
        if line.startswith("## "):
            groups.append((line[3:].strip(), []))
            continue
        for slug in re.findall(r"\]\((?:\./)?([A-Za-z0-9_-]+)\.md(?:#[^)]*)?\)", line):
            if slug in pages and slug not in seen:
                seen.add(slug)
                groups[-1][1].append(slug)
    return tuple((title, tuple(slugs)) for title, slugs in groups if slugs)


class Manual:
    """The guide's pages, read once from `directory`."""

    def __init__(self, pages: list[Page], groups: tuple[Group, ...] = ()) -> None:
        self.pages = pages
        self.groups = groups  # the page list's groups, by slug; pages in none stand alone
        self._by_slug = {p.slug: p for p in pages}

    def get(self, slug: str) -> Page:
        try:
            return self._by_slug[slug]
        except KeyError:
            raise ManualError(f"The guide has no page called {slug!r}.") from None

    def search(self, query: str) -> list[Result]:
        """Sections holding every word of `query` (any case), a match in the heading first,
        then in page order; at most `MAX_RESULTS`."""
        wanted = query.lower().split()
        if not wanted:
            return []
        found: list[tuple[int, Result]] = []
        for page in self.pages:
            for s in page.sections:
                head, body = s.heading.lower(), s.text.lower()
                if not all(w in head or w in body for w in wanted):
                    continue
                rank = 0 if all(w in head for w in wanted) else 1
                found.append((rank, Result(page.slug, page.title, s.heading, s.anchor,
                                           _snippet(s.text, wanted))))  # fmt: skip
        found.sort(key=lambda pair: pair[0])  # stable: page order within a rank
        return [r for _, r in found[:MAX_RESULTS]]


def _snippet(text: str, wanted: list[str]) -> str:
    """The part of a section around the first word found, cut at word ends."""
    lower = text.lower()
    at = min((lower.find(w) for w in wanted if w in lower), default=0)
    start = max(0, at - SNIPPET // 4)
    if start:
        start = text.find(" ", start) + 1
    cut = text[start : start + SNIPPET]
    if start + SNIPPET < len(text):
        cut = cut.rsplit(" ", 1)[0] + "…"
    return ("…" if start else "") + cut


def load_manual(directory: Path) -> Manual:
    """Every `*.md` page in `directory`: `README.md` first, then the pages it links to in
    that order (grouped by its sections), then any others by name. An empty or missing
    folder gives no pages."""
    files = {p.stem: p for p in sorted(directory.glob("*.md"))} if directory.is_dir() else {}
    texts = {stem: path.read_text(encoding="utf-8") for stem, path in files.items()}
    groups = _groups(texts.get(INDEX, ""), set(texts) - {INDEX})
    order = [INDEX] if INDEX in texts else []
    order += [s for _, slugs in groups for s in slugs]
    order += [s for s in texts if s not in order]
    pages = [render_page("" if s == INDEX else s, texts[s]) for s in order]
    return Manual(pages, groups)


def page_html(manual: Manual, page: Page) -> str:
    """The whole HTML page: the guide's pages, grouped by the first page's sections, and
    this page's headings on the left (with the search box), the page on the right. Styled
    by the app's theme and `manual.css`."""

    def item(p: Page) -> str:
        here = p.slug == page.slug
        current = ' aria-current="page"' if here else ""
        link = f'<a href="./{escape(p.slug)}"{current}>{escape(p.title)}</a>'
        if not here or not p.slug:  # the first page's sections are the groups themselves
            return link
        parts = [s for s in p.sections if s.level == 2 and s.anchor]
        return link + "".join(
            f'<a class="part" href="#{escape(s.anchor)}">{escape(s.heading)}</a>' for s in parts
        )

    by_slug = {p.slug: p for p in manual.pages}
    grouped = {s for _, slugs in manual.groups for s in slugs}
    nav = [item(by_slug[""])] if "" in by_slug else []
    for title, slugs in manual.groups:
        items = "".join(item(by_slug[s]) for s in slugs)
        if title:
            items = (
                f'<div class="manual-group"><p class="manual-group-title">{escape(title)}</p>'
                f"{items}</div>"
            )
        nav.append(items)
    nav += [item(p) for p in manual.pages if p.slug and p.slug not in grouped]
    return (
        "<!doctype html>\n"
        '<html lang="en"><head><meta charset="utf-8">'
        '<meta name="viewport" content="width=device-width, initial-scale=1">'
        f"<title>{escape(page.title)} · Solum Builder guide</title>"
        '<link rel="icon" href="../assets/brand/favicon-outlined.svg">'
        '<script src="../theme-start.js"></script>'
        '<link rel="stylesheet" href="../theme.css"><link rel="stylesheet" href="../manual.css">'
        '</head><body class="manual">'
        '<nav class="manual-nav" aria-label="Guide">'
        '<a class="manual-home" href="./">Solum Builder guide</a>'
        '<input id="manual-search" type="search" placeholder="Search the guide" '
        'aria-label="Search the guide" autocomplete="off">'
        '<div id="manual-results" class="manual-results" hidden></div>'
        f'<div id="manual-pages" class="manual-pages">{"".join(nav)}</div>'
        "</nav>"
        f'<main class="manual-page">{page.html}</main>'
        '<script type="module" src="../manual.js"></script>'
        "</body></html>\n"
    )
