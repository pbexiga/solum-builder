"""DECISIONS.md: every entry is numbered in order and tagged from the Tags table (D-306)."""

import re
from pathlib import Path

DECISIONS = Path(__file__).resolve().parents[2] / "docs" / "DECISIONS.md"
HEADING = re.compile(r"^\*\*D-(\d{3}) — .*?\*\*")
TAGS_AT_END = re.compile(r"((?: `[a-z]+`)+)$")


def known_tags(text: str) -> set[str]:
    """The tags listed in the Tags table."""
    table = text[text.index("## Tags") : text.index("\n---\n")]
    return set(re.findall(r"^\| `([a-z]+)` \|", table, re.M))


def entries(text: str) -> list[tuple[int, list[str], str]]:
    """(number, tags at the end of the heading, heading) for every entry."""
    found = []
    for line in text.splitlines():
        heading = HEADING.match(line)
        if heading:
            tags = TAGS_AT_END.search(line)
            used = re.findall(r"`([a-z]+)`", tags.group(1)) if tags else []
            found.append((int(heading.group(1)), used, line[:60]))
    return found


def test_entries_are_numbered_in_order_without_gaps() -> None:
    numbers = [n for n, _, _ in entries(DECISIONS.read_text())]
    assert numbers == list(range(1, len(numbers) + 1))


def test_every_entry_ends_with_known_tags() -> None:
    text = DECISIONS.read_text()
    tags = known_tags(text)
    assert {"project", "sim", "panes"} <= tags
    for _, used, heading in entries(text):
        assert used, f"no tags at the end of: {heading}"
        assert set(used) <= tags, f"unknown tag in: {heading}"
        assert len(used) == len(set(used)), f"repeated tag in: {heading}"


def test_every_listed_tag_is_used() -> None:
    text = DECISIONS.read_text()
    assert known_tags(text) == {t for _, used, _ in entries(text) for t in used}
