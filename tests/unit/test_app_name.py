"""The app calls itself "Solum Builder", never just "Solum" (the user's brand)."""

import re
from pathlib import Path

BARE = re.compile(r"Solum(?! Builder)")
TEXT = {".py", ".js", ".html", ".css", ".yaml", ".json", ".cir", ".lib", ".md"}
# The header's logo lockup sets the two words in different styles (DESIGN.md).
LOCKUP = '<span class="solum">Solum</span> <span class="builder">Builder</span>'
# View → Theme's first theme is named Solum (the user's name for it, D-303)
THEME_NAME = 'name: "Solum"'


def bare_names(root: Path) -> list[str]:
    """`path:line` of every bare "Solum" in the text files under `root`."""
    found = []
    for path in sorted(root.rglob("*")):
        if path.suffix not in TEXT or "vendor" in path.parts or "__pycache__" in path.parts:
            continue
        for number, line in enumerate(path.read_text(errors="replace").splitlines(), 1):
            if BARE.search(line.replace(LOCKUP, "").replace(THEME_NAME, "")):
                found.append(f"{path}:{number}")
    return found


def test_finds_a_bare_name(tmp_path: Path) -> None:
    (tmp_path / "a.py").write_text('ok = "Solum Builder"\nbad = "Solum can\'t"\n')
    (tmp_path / "b.html").write_text(LOCKUP)
    assert bare_names(tmp_path) == [f"{tmp_path / 'a.py'}:2"]


def test_the_app_always_names_itself_in_full(repo: Path) -> None:
    for folder in ("solum", "web", "library"):
        assert bare_names(repo / folder) == []
