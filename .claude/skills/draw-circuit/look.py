"""Look at a circuit file as the app shows it, without touching anyone's circuits: runs the
app on a free port with temporary folders, lists the file's Problems, prints its DC
voltages and saves a picture of the drawing beside the file (`<file>.png`).

Run in the dev image:
    make run CMD="python .claude/skills/draw-circuit/look.py scratch/drawn/my-boost.json"
Exit code 1 when the file can't be read or has an error-level problem.
"""

import argparse
import json
import os
import sys
import tempfile
from pathlib import Path
from typing import Any

from playwright.sync_api import Page, sync_playwright

from solum.api.serving import serving
from solum.config import load_settings

WIDTH, HEIGHT = 2400, 1400  # room for a pedal's whole schematic at a readable size


def said(answer: Any) -> str:
    """The plain message of a refusal from the app."""
    try:
        return str(answer.json().get("message") or answer.json().get("detail"))
    except ValueError:
        return str(answer.text())


def problems(page: Page, url: str, circuit: dict[str, Any]) -> bool:
    """Print the Problems pane's list; True when none is an error."""
    answer = page.request.post(f"{url}api/problems", data={"circuit": circuit})
    if not answer.ok:
        print(said(answer))
        return False
    found = answer.json()
    for p in found["problems"]:
        print(f"{p['severity'].upper()}: {p['title']}\n  {p['message']}\n  Fix: {p['fix']}")
    if not found["problems"]:
        print("Problems: none.")
    if not found["checked_op"]:
        print("The DC operating point was not checked (the drawing stops it, or it failed).")
    return not any(p["severity"] == "error" for p in found["problems"])


def voltages(page: Page, url: str, circuit: dict[str, Any]) -> None:
    """Print each net's DC voltage, as View → DC voltages shows them."""
    answer = page.request.post(f"{url}api/run", data={"circuit": circuit})
    if not answer.ok:
        print(said(answer))
        return
    dc = answer.json()["op"]["voltages"]
    print("DC: " + ", ".join(f"{net} {volts:.2f} V" for net, volts in sorted(dc.items())))


def picture(page: Page, url: str, circuit: dict[str, Any], out: Path) -> None:
    """Save the drawing as the editor shows it, fitted to the window."""
    saved = page.request.post(f"{url}api/circuits", data={"circuit": circuit})
    if not saved.ok:
        print(said(saved))
        return
    page.goto(f"{url}#circuit/{saved.json()['circuit']['id']}")
    page.wait_for_selector("#schematic g.part")
    page.wait_for_function("document.body.dataset.busy !== 'true'")
    page.locator("#schematic").screenshot(path=str(out))
    print(f"Picture: {out}")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("circuit", type=Path, help="circuit .json file")
    args = parser.parse_args()
    circuit = json.loads(args.circuit.read_text(encoding="utf-8"))
    with tempfile.TemporaryDirectory() as tmp:
        settings = load_settings(
            {**os.environ, "DATA_DIR": f"{tmp}/data", "CACHE_DIR": f"{tmp}/cache"}
        )
        with serving(settings) as url, sync_playwright() as p:
            browser = p.chromium.launch()
            page = browser.new_page(viewport={"width": WIDTH, "height": HEIGHT})
            good = problems(page, url, circuit)
            voltages(page, url, circuit)
            picture(page, url, circuit, args.circuit.with_suffix(".png"))
            browser.close()
    return 0 if good else 1


if __name__ == "__main__":
    sys.exit(main())
