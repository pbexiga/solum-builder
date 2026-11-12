"""Tools → Add a model (9c, solum/model_import.py): finding a file's cards, cleaning and
renaming the chosen one, its quick check (a stand-in measure here; real ngspice in
tests/sim/test_model_import.py), and saving it where the app loads user models."""

from pathlib import Path

import pytest

from solum.model_import import cards_in, make_model, save_model, suggested_id
from solum.models import Model, ModelError, ModelLibrary, load_model, load_models

LIBRARY = load_models([Path(__file__).parents[2] / "library" / "models"])

# LTspice's style: mfg and vceo are LTspice-only, ngspice rejects them (D-029)
FILE = """* a maker's library
.model Q2N3904X NPN(IS=1E-14 VAF=100 BF=300 IKF=0.4 XTB=1.5 BR=4 CJC=4E-12 mfg=Acme vceo=40)
.model D1N4148X D(IS=2.52n RS=.568 N=1.752 CJO=4p M=.4 tt=20n Iave=200m Vpk=75)
.subckt HELPER 1 2
R1 1 2 1k
.ends
* OPAX op-amp. Connections: out, in-, in+, V-, V+, offset null
.subckt OPAX 1 2 3 4 5 6 params: gain=1
.model QINNER NPN(IS=1E-16 mfg=Acme)
X1 1 2 HELPER
.ends OPAX
.param shared=2
.tran 1u 1m
.end
"""


def fake_measure(model: Model, models: ModelLibrary, quantity: str, c: dict[str, float]) -> float:
    assert model.id in models  # checked inside a library that holds it
    if quantity == "buffer_out":
        return c["vin"] - 1e-4
    return {"vf": 0.62, "tester_hfe": 250.0, "iceo": 0.0, "hfe": 280.0, "vbe": 0.66,
            "aol_db": 100.0, "gbw": 3e6, "swing_pos": 1.5, "swing_neg": 1.4}[quantity]  # fmt: skip


def test_a_files_cards_are_its_discrete_cards_and_op_amp_subcircuits() -> None:
    found = cards_in(FILE)
    assert [(f.name, f.spice_type, f.part_types) for f in found] == [
        ("Q2N3904X", "NPN", ("bjt",)), ("D1N4148X", "D", ("diode", "led")),
        ("OPAX", "SUBCKT", ("opamp",)),
    ]  # fmt: skip
    opax = found[2]  # HELPER has two nodes: no op-amp; the parameters aren't nodes
    assert opax.nodes == ("1", "2", "3", "4", "5", "6")
    assert opax.guess == ("+", "-", "V+", "V-", "out", "")  # the usual order, then none
    assert opax.comment == "* OPAX op-amp. Connections: out, in-, in+, V-, V+, offset null"
    with pytest.raises(ModelError, match=r"op-amp \.subckt"):
        cards_in(".subckt X 1 2\n.ends\n")


# OPAX's own order, as its comment says
OPAX_PINS = ["out", "-", "+", "V-", "V+", ""]


def test_an_op_amp_is_wrapped_in_the_usual_pin_order() -> None:
    added = make_model(FILE, "opax", "opamp", "OPAX-mine", "acme.lib", LIBRARY, fake_measure,
                       OPAX_PINS, channels=2)  # fmt: skip
    m = added.model
    assert m.info.kind == "subckt" and m.info.spice_name == "OPAX-mine"
    assert m.info.pins == ["+", "-", "V+", "V-", "out"] and m.halves == 2
    lines = m.card.splitlines()
    wrapper = lines.index(".subckt OPAX-mine inp inm vpos vneg out")
    assert lines[wrapper + 1 : wrapper + 3] == [
        "X1 out inm inp vneg vpos nc1 OPAX",
        "R_nc1 nc1 0 1e12",
    ]
    assert "* pins as the user set them (node pin): 1 out, 2 -, 3 +, 4 V-, 5 V+, 6 none" in lines
    assert lines[-1] == ".ends OPAX-mine"
    # the file's definitions go inside, cleaned; its commands stay out
    assert ".subckt HELPER 1 2" in lines and ".param shared=2" in lines
    assert ".model QINNER NPN(is=1E-16)" in lines and m.info.manufacturer == "Acme"
    assert lines[0].startswith("* OPAX from acme.lib, added by the user")
    assert not any(ln.startswith((".tran", ".end ")) or ln == ".end" for ln in lines)
    assert [(c["quantity"], c["at"]) for c in added.checks] == [
        ("buffer_out", "±4.5 V, in 500 mV"), ("buffer_out", "±4.5 V, in -500 mV"),
        ("swing_pos", "±4.5 V, into 10 kΩ"), ("swing_neg", "±4.5 V, into 10 kΩ"),
        ("aol_db", "±4.5 V"), ("gbw", "±4.5 V"),
    ]  # fmt: skip
    assert m.chip_spec() == {"type": "opamp", "halves": 2, "simulated": m.info.pins,
                             "package": None}  # fmt: skip


def test_an_op_amps_pins_go_on_one_node_each() -> None:
    for pins in (["+", "-", "V+", "V-", "out"], ["+", "+", "V+", "V-", "out", ""],
                 ["+", "-", "V+", "V-", "", ""]):  # fmt: skip
        with pytest.raises(ModelError, match="once each"):
            make_model(FILE, "OPAX", "opamp", "O", "acme.lib", LIBRARY, fake_measure, pins)
    with pytest.raises(ModelError, match="one, two or four"):
        make_model(FILE, "OPAX", "opamp", "O", "acme.lib", LIBRARY, fake_measure, OPAX_PINS, 3)


def test_an_op_amp_that_doesnt_follow_as_a_buffer_has_its_pins_wrong() -> None:
    def railed(model: Model, models: ModelLibrary, quantity: str, c: dict[str, float]) -> float:
        return 3.9  # stuck at a rail: the output or a supply on the wrong node

    with pytest.raises(ModelError, match=r"doesn't follow its input .* pin order is probably"):
        make_model(FILE, "OPAX", "opamp", "O", "acme.lib", LIBRARY, railed)

    def swapped(model: Model, models: ModelLibrary, quantity: str, c: dict[str, float]) -> float:
        # + and - swapped: the buffer still balances at DC, but open loop the output goes
        # to the far rail, 1.5 V short of it: 7.5 V from the near one on ±4.5 V
        return fake_measure(model, models, quantity, c) if quantity == "buffer_out" else 7.5

    with pytest.raises(ModelError, match=r"With \+ above −, OPAX's output goes the other way"):
        make_model(FILE, "OPAX", "opamp", "O", "acme.lib", LIBRARY, swapped)


def test_an_added_card_is_cleaned_renamed_and_checked() -> None:
    added = make_model(FILE, "q2n3904x", "bjt", "2N3904-mine", "acme.lib", LIBRARY, fake_measure)
    m = added.model
    assert m.id == "2N3904-mine" and m.info.spice_name == "2N3904-mine"
    assert m.statement is not None and m.statement.name == "2N3904-mine"
    assert "mfg" not in m.statement.params and m.info.manufacturer == "Acme"
    assert m.info.ratings == {"vceo": 40.0}
    assert "moved mfg=Acme out of the card into metadata" in added.fixes
    assert [c["quantity"] for c in added.checks] == ["tester_hfe", "iceo", "hfe", "vbe"]
    assert all(c["plausible"] for c in added.checks)
    assert [(c["name"], c["text"], c["at"]) for c in added.checks] == [
        ("Gain on the tester", "250", "on the 9 V tester"),
        ("Leakage (ICEO)", "0 A", "on the 9 V tester"),
        ("hFE", "280", "IC 1 mA, VCE 5 V"), ("VBE(on)", "660 mV", "IC 1 mA, VCE 5 V"),
    ]  # fmt: skip
    assert m.bjt_spec() == {"hfe": 250.0, "leakage": 0.0, "germanium": False}
    assert m.catalogue_entry()["origin"] == "user"
    assert m.info.source.card == "Q2N3904X"  # as the file spells it: the parts list matches it
    assert "2N3904-mine" not in LIBRARY  # the check never touches the app's library


def test_an_added_card_must_fit_its_part_and_a_free_name() -> None:
    cases = [
        ("Q2N3904X", "diode", "x", "it can't be a diode"),
        ("NOPE", "bjt", "x", "no card called NOPE"),
        ("Q2N3904X", "bjt", "2N3904", "already a model called 2N3904"),
        ("Q2N3904X", "bjt", "2n3904", "already a model called 2N3904"),  # ngspice: one name
        ("Q2N3904X", "bjt", "two words", "letters, digits"),
    ]
    for name, part, mid, message in cases:
        with pytest.raises(ModelError, match=message):
            make_model(FILE, name, part, mid, "acme.lib", LIBRARY, fake_measure)  # type: ignore[arg-type]


def test_a_value_out_of_range_is_flagged_not_refused() -> None:
    def low(model: Model, models: ModelLibrary, quantity: str, c: dict[str, float]) -> float:
        return 0.01  # a diode at 10 mV: something's wrong with the card

    added = make_model(FILE, "D1N4148X", "diode", "1N4148-acme", "acme.lib", LIBRARY, low)
    assert [c["plausible"] for c in added.checks] == [False, False]


def test_a_saved_model_loads_back_and_joins_the_library(tmp_path: Path) -> None:
    added = make_model(FILE, "D1N4148X", "led", "LED-acme", "acme.lib", LIBRARY, fake_measure)
    path = save_model(added.model, tmp_path)
    assert path == tmp_path / "models" / "led" / "LED-acme.json"
    back = load_model(path)
    assert back.info == added.model.info and back.card == added.model.card
    lib = load_models([tmp_path / "models"])
    shared = lib.with_fitter(lib.bjt_fit)
    before = lib.fingerprint
    lib.add(Model(info=back.info.model_copy(update={"id": "X"}), card=back.card))
    assert "X" in shared and shared.fingerprint != before  # one library, one fingerprint


def test_a_cards_name_starts_as_its_own_or_mine_when_taken() -> None:
    """9c: Add a model's name starts as the card's own, or `<card>-mine` when a model has
    it (in any case: 2n3904 would read as the stock 2N3904); a stock model is never replaced."""
    lib = ModelLibrary({k: LIBRARY.get(k) for k in ("2N3904", "1N4148")})
    assert suggested_id("Q2N3904X", lib) == "Q2N3904X"
    assert suggested_id("2n3904", lib) == "2n3904-mine"
    lib.add(Model(info=LIBRARY.get("1N4148").info.model_copy(update={"id": "1N4148-mine"}),
                  card=""))  # fmt: skip
    assert suggested_id("1N4148", lib) == "1N4148-mine-2"
    assert suggested_id("A" * 40, lib) == "A" * 40
    long = "B" * 40
    lib.add(Model(info=LIBRARY.get("1N4148").info.model_copy(update={"id": long}), card=""))
    assert suggested_id(long, lib) == "B" * 35 + "-mine"  # still a valid name (40 at most)


def test_a_user_model_is_yours() -> None:
    added = make_model(FILE, "D1N4148X", "diode", "1N4148-acme", "acme.lib", LIBRARY, fake_measure)
    assert added.model.yours and not LIBRARY.get("1N4148").yours
