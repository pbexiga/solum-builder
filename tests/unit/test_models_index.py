import importlib.util
from pathlib import Path

SCRIPT = Path(__file__).parents[2] / "scripts" / "models_index.py"
_spec = importlib.util.spec_from_file_location("models_index", SCRIPT)
assert _spec and _spec.loader
index = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(index)

KSL = "https://github.com/kicad-spice-library/KiCad-Spice-Library/blob/x/Models/"


def record(url: str, original: str = "Philips", licence: str = "GPL") -> dict:
    return {"source": {"url": url, "licence": licence, "original": original}}


def test_the_committed_shipped_table_matches_the_records() -> None:
    text = index.INDEX.read_text(encoding="utf-8")
    assert index.with_table(text, index.shipped_table()) == text, (
        "run python3 scripts/models_index.py"
    )


def test_a_makers_card_in_ltspices_file_waits_for_a_decision() -> None:
    status = index.licence_status(record(KSL + "Transistor/BJT/BJT.lib"))
    assert status.startswith("Decide: the maker's model inside LTspice's library")


def test_an_unnamed_card_in_ltspices_file_is_off_limits() -> None:
    for original in ("", "unattributed (MFG=GERMANIUM-TYPE)"):
        status = index.licence_status(record(KSL + "Diode/DIODE2.lib", original))
        assert "off limits under D-152" in status


def test_intusofts_file_is_off_limits_whoever_made_the_card() -> None:
    status = index.licence_status(record(KSL + "Transistor/FET/JFET.LIB", "Siliconix"))
    assert "off limits under D-151" in status


def test_makers_own_files_are_settled() -> None:
    assert index.licence_status(record(KSL + "x/phil_fet.lib")).startswith("Settled")
    ti = index.licence_status(record(KSL + "Manufacturer/Texas%20Instruments/tl071.mod",
                                     "Texas Instruments"))  # fmt: skip
    assert ti == "Settled: Texas Instruments' own model, no notice"


def test_non_commercial_and_unsettled_terms_wait_for_a_decision() -> None:
    nc = index.licence_status(record("https://www.electrosmash.com/x", licence="CC BY-NC 3.0"))
    assert nc == "Decide: CC BY-NC (non-commercial only)"
    ti = record("https://www.ti.com/x", licence="TI's terms (redistribution to settle in 9e)")
    assert index.licence_status(ti).startswith("Decide: the maker's terms")


def test_the_table_replaces_only_its_own_block() -> None:
    text = f"intro\n{index.START}\nold\n{index.END}\nrest\n"
    expected = f"intro\n{index.START}\n| new |\n{index.END}\nrest\n"
    assert index.with_table(text, "| new |") == expected


def test_the_card_column_says_whose_card_it_is() -> None:
    ours = {"source": {"url": "https://x/sheet.pdf", "original": "Solum Builder fit"},
            "fit": {"sheet": "onsemi 2N3904 data sheet, Rev. 2"}}  # fmt: skip
    assert index.card(ours) == "Ours (fitted from onsemi 2N3904 data sheet, Rev. 2)"
    guess = {"source": {"url": "https://x/xref.pdf", "original": "Solum Builder estimate"},
             "fit": {"sheet": "no OC81D curve sheet: our OC75 fit scaled"}}  # fmt: skip
    assert index.card(guess) == "Estimated (no OC81D curve sheet: our OC75 fit scaled)"
    ksl = index.card(record(KSL + "Transistor/BJT/BJT.lib"))
    assert ksl == "Pulled (KiCad-Spice-Library, BJT.lib)"
    es = record("https://www.electrosmash.com/fuzz-face", "ElectroSmash Fuzz Face analysis")
    assert index.card(es) == "Pulled (ElectroSmash Fuzz Face analysis)"
