"""Tools → Add a model through real ngspice (9c): an LTspice-style card from a maker's
file is cleaned, renamed and measured, and its figures are a real part's."""

import time
from pathlib import Path

import pytest

from solum import model_checks
from solum.circuit.build import CircuitBuilder
from solum.model_import import check_apart, engine_measure, make_model
from solum.models import ModelError, ModelLibrary, load_models
from solum.netlist import Op, generate_netlist
from solum.sim.native import NativeNgspice
from tests.unit.test_model_import import FILE

pytestmark = pytest.mark.sim
LIBRARY = load_models([Path(__file__).parents[2] / "library" / "models"])


def test_a_makers_cards_check_as_real_parts(engine: NativeNgspice) -> None:
    measure = engine_measure(engine)
    q = make_model(FILE, "Q2N3904X", "bjt", "Q-acme", "acme.lib", LIBRARY, measure)
    got = {c["quantity"]: c["value"] for c in q.checks}
    assert all(c["plausible"] for c in q.checks)
    assert 0.55 < got["vbe"] < 0.75  # a silicon junction at 1 mA
    assert 280 < got["hfe"] < 300 * (1 + 5 / 100)  # BF 300, lifted by VCE 5 V over VAF 100
    d = make_model(FILE, "D1N4148X", "diode", "D-acme", "acme.lib", LIBRARY, measure)
    vf = [c["value"] for c in d.checks]
    assert 0.55 < vf[0] < vf[1] < 0.9  # 1 mA, then 10 mA


# TI's own 1989 TL072 file, as a user would add it (the library's TL072 is our own card, D-219)
TL072 = (Path(__file__).parents[1] / "fixtures" / "models" / "TL072_TI_1989.lib").read_text()


def test_a_makers_op_amp_checks_as_the_same_part(engine: NativeNgspice) -> None:
    """TI's TL072 file, added under another name, measures as the stock TL072 does (ours,
    built from the same sheet's typicals, D-219: so to within a dB and a few %); with its
    inputs swapped it's refused; both run side by side in one netlist (the user's copy of
    `.subckt TL072` stays inside its wrapper)."""
    measure = engine_measure(engine)
    added = make_model(TL072, "TL072", "opamp", "TL072-mine", "tl072.lib", LIBRARY, measure)
    got = {(c["quantity"], c["at"]): c["value"] for c in added.checks}
    assert all(c["plausible"] for c in added.checks)
    assert got[("buffer_out", "±4.5 V, in 500 mV")] == pytest.approx(0.5, abs=5e-3)
    stock = LIBRARY.get("TL072")
    at = {"supply": 4.5}
    ours = {q: model_checks.measure(engine, LIBRARY, stock, q, at) for q in ("aol_db", "gbw")}
    assert got[("aol_db", "±4.5 V")] == pytest.approx(ours["aol_db"], abs=1.5)
    assert got[("gbw", "±4.5 V")] == pytest.approx(ours["gbw"], rel=0.05)
    with pytest.raises(ModelError, match="pin order is probably wrong"):
        make_model(TL072, "TL072", "opamp", "T", "tl072.lib", LIBRARY, measure,
                   ["-", "+", "V+", "V-", "out"])  # fmt: skip
    both = ModelLibrary({**{i: LIBRARY.get(i) for i in LIBRARY.ids()}, "TL072-mine": added.model})
    b = (
        CircuitBuilder("both")
        .part("V1", "vsource", "VP", "0", value=4.5)
        .part("V2", "vsource", "VN", "0", value=-4.5)
        .part("V3", "vsource", "p", "0", value=0.3)
        .part("U1", "opamp", "p", "o1", "o1", model="TL072", supply=("VP", "VN"))
        .part("U2", "opamp", "o1", "o2", "o2", model="TL072-mine", supply=("VP", "VN"))
    )  # fmt: skip
    netlist = generate_netlist(b.build(), both, Op())
    vectors = engine.run(netlist.text).plot("op").vectors
    assert float(vectors[netlist.node("o2")][0].real) == pytest.approx(0.3, abs=5e-3)


def test_a_check_that_sets_ngspice_spinning_is_stopped_apart(engine: NativeNgspice) -> None:
    """D-195: TL072 with this wrong pin order sets ngspice's DC solve spinning past any
    halt. Checked in a process of its own, it's stopped and refused in words, and the
    app's ngspice never saw it: it still runs at once. A good order checks the same way."""
    started = time.monotonic()
    with pytest.raises(ModelError, match=r"got stuck on TL072 .* pin order is probably wrong"):
        check_apart(TL072, "TL072", "opamp", "T", "tl072.lib", LIBRARY,
                    ["-", "V+", "V-", "out", "+"], timeout=8.0)  # fmt: skip
    assert time.monotonic() - started < 15.0
    diode = LIBRARY.get("1N4148")
    assert 0.5 < model_checks.measure(engine, LIBRARY, diode, "vf", {"if": 1e-3}) < 0.8
    added = check_apart(TL072, "TL072", "opamp", "TL072-apart", "tl072.lib", LIBRARY)
    assert added.model.info.pins == ["+", "-", "V+", "V-", "out"]
    assert all(c["plausible"] for c in added.checks)
