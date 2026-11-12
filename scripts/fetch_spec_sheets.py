"""Download any datasheet listed in data/spec-sheets/README.md that isn't on disk (D-149).

The PDFs are gitignored; the index is committed, so a fresh clone fetches them with
`python3 scripts/fetch_spec_sheets.py`. Some makers refuse scripted downloads: those are
reported, to fetch by hand from the listed URL.
"""

import sys
import urllib.request
from pathlib import Path

SHEETS = Path(__file__).resolve().parents[1] / "data" / "spec-sheets"


def listed_sheets(index: str) -> list[tuple[str, str]]:
    """(file, url) for each row of the index's Sheets table."""
    rows: list[tuple[str, str]] = []
    in_sheets = False
    for line in index.splitlines():
        if line.startswith("## "):
            in_sheets = line.strip() == "## Sheets"
            continue
        cells = [c.strip() for c in line.strip().strip("|").split("|")]
        if in_sheets and len(cells) >= 3 and cells[1].endswith(".pdf"):
            rows.append((cells[1], cells[2].split()[0]))  # a note may follow the URL
    return rows


def main() -> int:
    failed = 0
    for name, url in listed_sheets((SHEETS / "README.md").read_text(encoding="utf-8")):
        path = SHEETS / name
        if path.exists():
            continue
        request = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
        try:
            with urllib.request.urlopen(request, timeout=60) as response:
                data = response.read()
        except OSError as err:
            print(f"{name}: couldn't download ({err}); fetch it by hand from {url}")
            failed += 1
            continue
        if not data.startswith(b"%PDF"):
            print(f"{name}: the site didn't send a PDF; fetch it by hand from {url}")
            failed += 1
            continue
        path.write_bytes(data)
        print(f"{name}: downloaded")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
