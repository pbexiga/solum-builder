import importlib.util
from pathlib import Path

SCRIPT = Path(__file__).parents[2] / "scripts" / "fetch_spec_sheets.py"
_spec = importlib.util.spec_from_file_location("fetch_spec_sheets", SCRIPT)
assert _spec and _spec.loader
fetch = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(fetch)


def test_only_the_sheets_table_is_read() -> None:
    index = (
        "# Datasheets\n\n## Sheets\n\n| Part | File | URL | Retrieved |\n|---|---|---|---|\n"
        "| TL061 | TL06x.pdf | https://example.com/tl061.pdf | 2026-10-29 |\n\n"
        "## Not shipped\n\n| Part | Missing |\n|---|---|\n| OC44 | x.pdf |\n"
    )
    assert fetch.listed_sheets(index) == [("TL06x.pdf", "https://example.com/tl061.pdf")]


def test_the_committed_index_lists_files_with_urls() -> None:
    rows = fetch.listed_sheets((fetch.SHEETS / "README.md").read_text(encoding="utf-8"))
    assert rows
    assert all(url.startswith("https://") and " " not in url for _, url in rows)
    assert len({name for name, _ in rows}) == len(rows)


def test_a_note_after_the_url_is_not_part_of_it() -> None:
    index = (
        "## Sheets\n\n| Part | File | URL | Retrieved |\n|---|---|---|---|\n"
        "| 2N5087 | x.pdf | https://example.com/x.pdf (Central's sheet, mirrored) | 2026-10-29 |\n"
    )
    assert fetch.listed_sheets(index) == [("x.pdf", "https://example.com/x.pdf")]
