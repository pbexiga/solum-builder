"""Cards we may not ship (9c, solum/not_included.py): the list in library/models, each with
whose terms keep it out and where to get it, left out of the parts list once it's in."""

import json
from pathlib import Path

import pytest

from solum.model_import import make_model
from solum.models import Model, ModelError, ModelLibrary, load_models
from solum.not_included import catalogue_entries, load_not_included

CORE = Path(__file__).parents[2] / "library" / "models"
LISTING = load_not_included(CORE)
ELECTROSMASH = ".model GERPNP_HIGHGAIN PNP(is=120.8N bf=120 nf=1 vaf=102 rb=173)\n"


def _measure(_m: Model, _lib: ModelLibrary, quantity: str, _c: dict[str, float]) -> float:
    return {"tester_hfe": 120.0, "iceo": 2e-4, "hfe": 118.0, "vbe": 0.2}[quantity]


def test_the_list_has_every_decide_card_and_nationals_lm13700() -> None:
    """D-156's 28 *Decide* cards (by the index at 255503c) and National's LM13700 (D-183),
    each with a file or page to get it from."""
    ids = [c.id for c in LISTING.cards]
    assert len(ids) == 29 and len(set(ids)) == 29
    assert {"2N3904", "AC128-B120", "AC128-B85", "J201", "TLC2262", "LM13700"} <= set(ids)
    assert all(c.url.startswith("https://") for c in LISTING.cards)
    kicad = [c for c in LISTING.cards if "kicad-spice-library" in c.url]
    assert all(c.url.endswith(c.file) and "/a8688952" in c.url for c in kicad)  # the pinned commit
    assert next(c for c in LISTING.cards if c.id == "BAT46").card == "BAT46WJ"


def test_an_entry_says_why_and_what_to_get() -> None:
    lib = load_models([CORE])
    entries = {e["id"]: e for e in catalogue_entries(LISTING, lib)}
    e = entries["2N3904"]  # our own fit ships under this id; Philips' card doesn't
    assert e["origin"] == "excluded" and e["type"] == "bjt" and e["card"] == "2N3904"
    assert "Analog Devices" in e["why"] and "all rights reserved" in e["why"]
    assert e["get"].startswith("the file BJT.lib from KiCad-Spice-Library")
    assert "CC BY-NC" in entries["AC128-B120"]["why"]
    assert "{file}" not in "".join(x["get"] for x in entries.values())
    assert "SNOM267.ZIP" in entries["LM13700"]["get"]


def test_the_cards_taken_out_in_the_licence_audit_are_listed() -> None:
    """The 2N4123, 2N4125, AC127 and BC109C cards are LTspice's own; no starter or block
    uses them, so they left the library in 9e's licence audit (D-288) and are listed as
    not included, like the rest."""
    ids = {e["id"] for e in catalogue_entries(LISTING, load_models([CORE]))}
    assert {"2N4123", "2N4125", "AC127", "BC109C"} <= ids
    # a stock model of that id from another card doesn't hide it: our own fits (D-253)
    assert {"2N3904", "1N34A"} <= ids


def test_the_users_copy_shows_instead() -> None:
    """Once added with Add a model (under any name), the entry for that card goes."""
    core = load_models([CORE])
    added = make_model(ELECTROSMASH, "gerpnp_highgain", "bjt", "AC128-mine", "fuzz.lib", core,
                       _measure).model  # fmt: skip
    lib = ModelLibrary({**{i: core.get(i) for i in core.ids()}, added.id: added})
    ids = {e["id"] for e in catalogue_entries(LISTING, lib)}
    assert "AC128-B120" not in ids and "AC128-B85" in ids


def test_a_missing_list_is_empty_and_a_broken_one_says_so(tmp_path: Path) -> None:
    assert load_not_included(tmp_path).cards == []
    card = {"id": "X", "type": "bjt", "card": "X", "description": "", "maker": "",
            "source": "nowhere", "file": "", "url": ""}  # fmt: skip
    bad = {"sources": {}, "cards": [card]}
    (tmp_path / "not-included.json").write_text(json.dumps(bad))
    with pytest.raises(ModelError, match="can't be used"):
        load_not_included(tmp_path)
