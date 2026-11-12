"""Netlist generation: per-part elements, node naming, analyses, and snapshots.

Snapshots live in tests/fixtures/netlists/. A changed netlist fails the test; review the
diff, then regenerate with `SOLUM_UPDATE_SNAPSHOTS=1 make test` (AGENTS.md: never update
blindly).
"""

import os
import re
from collections.abc import Callable
from dataclasses import replace
from pathlib import Path

import pytest

from solum.circuit.build import CircuitBuilder
from solum.circuit.io import load_circuit
from solum.circuit.schema import Capacitor, ChargePump
from solum.models import ModelLibrary, load_models
from solum.netlist import (
    Ac,
    Dc,
    NetlistError,
    Op,
    Tran,
    element_name,
    generate_netlist,
    node_names,
    part_elements,
    pump_resistance,
)

TESTS = Path(__file__).parents[1]
SNAPSHOTS = TESTS / "fixtures" / "netlists"
Builder = Callable[..., CircuitBuilder]


@pytest.fixture(scope="module")
def models() -> ModelLibrary:
    return load_models([TESTS.parent / "library" / "models"])


def every_part(circuit: Builder) -> CircuitBuilder:
    """One of each part type, wired into something plausible."""
    return (
        circuit("every part")
        .rail("V+", 9.0)
        .part(
            "IN",
            "guitar",
            "in",
            source="pickup",
            pickup={"r": "6k", "l": 2.5, "c": "500p"},
            cable=3,
            volume="250k",
            rotation=0.5,
        )
        .part("C1", "capacitor", "in", "b", value="100n")
        .part("R1", "resistor", "b", "VREF", value="1M")
        .part("R2", "resistor", "V+", "VREF", value="10k")
        .part("R3", "resistor", "VREF", "0", value="10k")
        .part("U1", "opamp", "b", "fb", "o", model="LM308", pins={"comp1": "c1", "comp2": "c2"})
        .part("C3", "capacitor", "c1", "c2", value="30p")
        .part("VR1", "pot", "fb", "fb", "o", value="100k", taper="A", rotation=0.25)
        .part("R4", "resistor", "fb", "e", value="560")
        .part("C2", "capacitor", "e", "0", value="4u7", kind="electrolytic")
        .part("D1", "diode", "o", "0", model="1N4148")
        .part("D2", "diode", "0", "o", model="1N4148")
        .part("SW1", "switch", pins={"2": "o", "1": "t1", "3": "t2"}, position=1)
        .part("Q1", "jfet", "V+", "t2", "s", model="J201", measured={"idss": 6e-4, "vp": -0.8})
        .part("TR1", "trimmer", "s", "s", "0", value="10k", rotation=0.3)
        .part("Q2", "bjt", "V+", "s", "out", model="2N5089")
        .part("L1", "inductor", "out", "lo", value="500m", resistance=20)
        .part("R5", "resistor", "lo", "0", value="10k")
        .part("Q3", "mosfet", "sw", "VREF", "0", model="2N7000")
        .part("R6", "resistor", "V+", "sw", value="10k")
        .part("V1", "vsource", "t1", "0", value=-1.5)
        .part("OUT", "amp", "out")
    )


def check_snapshot(name: str, text: str) -> None:
    path = SNAPSHOTS / f"{name}.cir"
    if os.environ.get("SOLUM_UPDATE_SNAPSHOTS") == "1":
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text)
    assert path.exists(), f"No snapshot {path.name}; run with SOLUM_UPDATE_SNAPSHOTS=1."
    assert text == path.read_text(), f"{path.name} changed: review the diff, then update."


@pytest.mark.parametrize(
    ("name", "analysis"),
    [
        ("every-part-op", Op()),
        ("every-part-ac", Ac()),
        ("every-part-tran", Tran(freq=200, amplitude=0.3, stop=0.1, max_step=12.5e-6,
                                 save=("in", "out"))),
        ("every-part-dc", Dc("V1", -2, 0, 0.5)),
        ("every-part-recording", Tran(freq=0, amplitude=0, stop=5.0, max_step=1 / 96000,
                                      save=("out",), source_file="/cache/audio/src/ab.txt",
                                      gain=0.25)),
    ],
)  # fmt: skip
def test_every_part_snapshot(
    name: str, analysis: Op | Ac | Tran | Dc, models: ModelLibrary, circuit: Builder
) -> None:
    check_snapshot(name, generate_netlist(every_part(circuit).build(), models, analysis).text)


def test_a_recording_with_a_quote_in_its_path_is_refused(
    models: ModelLibrary, circuit: Builder
) -> None:
    rec = Tran(0, 0, 1.0, 1e-5, source_file='/tmp/a"b.txt')
    with pytest.raises(NetlistError, match="file name"):
        generate_netlist(every_part(circuit).build(), models, rec)


def test_hand_drawn_fixture_snapshot(models: ModelLibrary) -> None:
    c = load_circuit(TESTS / "fixtures" / "circuits" / "jfet-drive.json")
    check_snapshot("jfet-drive-ac", generate_netlist(c, models, Ac()).text)


def test_generation_is_deterministic(models: ModelLibrary, circuit: Builder) -> None:
    c = every_part(circuit).build()
    assert generate_netlist(c, models, Ac()).text == generate_netlist(c, models, Ac()).text


def test_pot_halves_and_switch_contacts(models: ModelLibrary, circuit: Builder) -> None:
    lines = generate_netlist(every_part(circuit).build(), models, Op()).text.splitlines()
    assert "R_VR1_a fb fb 5000" in lines  # A taper at 25 %: 5 % of 100k
    assert "R_VR1_b fb o 95000" in lines
    assert "R_SW1_1 o t1 1e+12" in lines  # position 1 (the second) joins lug 3
    assert "R_SW1_3 o t2 0.01" in lines


def test_an_inductor_is_its_coil_and_its_wire(models: ModelLibrary, circuit: Builder) -> None:
    """D-173: L1's wire resistance in series on pin 1's side; an ideal coil is L alone."""
    lines = generate_netlist(every_part(circuit).build(), models, Op()).text.splitlines()
    assert "R_L1_wire out l1_wire 20" in lines
    assert "L1 l1_wire lo 0.5" in lines
    ideal = circuit().part("IN", "guitar", "in").part("L2", "inductor", "in", "0", value="10m")
    assert "L2 in 0 0.01" in generate_netlist(ideal.build(), models, Op()).text.splitlines()


def test_a_mosfet_is_a_vdmos(models: ModelLibrary, circuit: Builder) -> None:
    """D-175: M, drain gate source, and its VDMOS card."""
    text = generate_netlist(every_part(circuit).build(), models, Op()).text
    assert "M_Q3 sw vref 0 2N7000" in text.splitlines()
    assert ".model 2N7000 VDMOS(" in text
    assert "@m_q3[id]" in text  # its drain current is read at the operating point


def chips(circuit: Builder) -> CircuitBuilder:
    """D-180: a 4049 stage (one inverter biased, the spares' inputs grounded), an LM13700
    VCA through its diodes and buffer (half b spare), and a CA3080 single."""
    b = circuit("chips").rail("V+", 9.0).part("IN", "guitar", "in")
    b.part("C1", "capacitor", "in", "a", value="100n").part("R1", "resistor", "a", "x", value="1M")
    b.part("IC1A", "inverter", "a", "x", model="CD4049UB", half="a")
    for unit in "bcdef":
        b.part(f"IC1{unit.upper()}", "inverter", "0", model="CD4049UB", half=unit)
    b.part("R2", "resistor", "V+", "VREF", value="10k")
    b.part("R3", "resistor", "VREF", "0", value="10k")
    b.part("R4", "resistor", "x", "p", value="10k").part("R5", "resistor", "p", "VREF", value="470")
    b.part("IC2A", "ota", "p", "VREF", "o", "ib", "d", "o", "y", model="LM13700", half="a")
    b.part("IC2B", "ota", model="LM13700", half="b")
    b.part("R6", "resistor", "V+", "ib", value="33k").part("R7", "resistor", "V+", "d", value="4k7")
    b.part("R8", "resistor", "o", "VREF", value="10k").part("R9", "resistor", "y", "0", value="10k")
    b.part("IC3", "ota", "y", "VREF", "out", "ib3", model="CA3080")
    b.part("R10", "resistor", "V+", "ib3", value="100k")
    b.part("R11", "resistor", "out", "VREF", value="10k")
    return b.part("OUT", "amp", "out")


def test_chip_units_are_their_subcircuits(models: ModelLibrary, circuit: Builder) -> None:
    """D-180: each used unit is an X instance on its own pins and the chip's supply (the
    power unit's for a 4049 or an LM13700, a CA3080's own); spare units are left out."""
    text = generate_netlist(chips(circuit).build(), models, Op()).text
    lines = text.splitlines()
    assert "X_IC1A a x v_ 0 CD4049UB_INV" in lines
    assert "X_IC2A p vref o ib d o y v_ 0 LM13700_OTA" in lines
    assert "X_IC3 y vref out ib3 v_ 0 CA3080" in lines
    assert "IC2B" not in text
    check_snapshot("chips-op", text)


def test_a_jack_is_left_out(models: ModelLibrary, circuit: Builder) -> None:
    """D-174: drawing only; its nets are the guitar's and ground's, nothing added."""
    plain = circuit().part("IN", "guitar", "in").part("R1", "resistor", "in", "0", value="1M")
    jacked = circuit().part("IN", "guitar", "in").part("R1", "resistor", "in", "0", value="1M")
    jacked.part("J1", "jack", "in", "0", stereo=True, label="Input")
    assert (
        generate_netlist(jacked.build(), models, Op()).text
        == generate_netlist(plain.build(), models, Op()).text
    )


def test_measured_jfet_gets_its_own_card(models: ModelLibrary, circuit: Builder) -> None:
    text = generate_netlist(every_part(circuit).build(), models, Op()).text
    assert "J_Q1 v_ t2 s J201_Q1" in text  # a JFET called Q1 is element J_Q1
    # Level-1 JFET: Idss = BETA * VTO^2, so BETA = 0.6 mA / 0.8^2
    assert "vto=-0.8" in text and "beta=0.0009375" in text


def test_measured_bjt_gets_its_own_card(models: ModelLibrary, circuit: Builder) -> None:
    """D-130: a copy of the card with BF from the measured hFE, the rest the model's."""
    c = (
        circuit()
        .part("Q1", "bjt", "c", "b", "0", model="AC128", measured={"hfe": 64})
        .part("Q2", "bjt", "c", "b", "0", model="AC128")
        .build()
    )
    text = generate_netlist(c, models, Op()).text
    assert "Q1 c b 0 AC128_Q1" in text and "Q2 c b 0 AC128" in text
    card = next(x for x in text.split(".model")[1:] if x.startswith(" AC128_Q1 "))
    assert "bf=64" in card and "is=2.909e-05" in card and "bf=107.8" not in card
    sub = circuit().part("U1", "opamp", "a", "b", "o", model="TL072").build()
    assert "TL072" in generate_netlist(sub, models, Op()).text  # no BJT: nothing to copy


def test_a_measured_leakage_is_a_hidden_collector_base_current(
    models: ModelLibrary, circuit: Builder
) -> None:
    """D-130: Icbo = (yours - the model's) / (hFE + 1), from the N side to the P side
    inside the part: base to collector in a PNP. The AC128 leaks 315.164 µA on the tester:
    415.164 µA measured at hFE 99 is 1 µA; less than the model's is a negative current."""

    def leak(model: str, **measured: float) -> list[str]:
        c = circuit().part("Q1", "bjt", "c", "b", "e", model=model, measured=measured)
        text = generate_netlist(c.build(), models, Op()).text
        return [x for x in text.splitlines() if x.startswith("I_Q1_leak")]

    assert leak("AC128", hfe=99, leakage=415.164e-6) == ["I_Q1_leak b c DC 1e-06"]
    assert leak("2N3904", hfe=199, leakage=20e-6) == ["I_Q1_leak c b DC 1e-07"]  # NPN
    assert leak("AC128", hfe=99) == []  # no leakage given: the model's own
    assert leak("AC128", hfe=99, leakage=315.164e-6) == []  # exactly the model's
    assert leak("AC128", hfe=99, leakage=310.164e-6) == ["I_Q1_leak b c DC -5e-08"]


def test_op_saves_device_currents(models: ModelLibrary, circuit: Builder) -> None:
    text = generate_netlist(every_part(circuit).build(), models, Op()).text
    assert ".save all @d1[id] @d2[id] @j_q1[id] @q2[ic] @q2[ib]" in text


def test_spst_switch(models: ModelLibrary, circuit: Builder) -> None:
    def contact(position: int) -> str:
        c = circuit().part("SW1", "switch", pins={"1": "a", "2": "b"}, kind="spst",
                           position=position).build()  # fmt: skip
        return generate_netlist(c, models, Op()).text.splitlines()[1]

    assert contact(0).endswith(" 1e+12")
    assert contact(1).endswith(" 0.01")


def test_node_names_are_safe_and_unique() -> None:
    names = node_names(["GND", "V+", "v-", "OUT", "out", "Q1.D", "0", "+"])
    assert names["GND"] == "0"
    assert names["V+"] == "v_"
    assert names["v-"] == "v__2"
    assert {names["OUT"], names["out"]} == {"out", "out_2"}
    assert names["Q1.D"] == "q1_d"
    assert names["0"] == "n0"
    assert len(set(names.values())) == len(names)


@pytest.mark.parametrize(
    ("letter", "ref", "suffix", "name"),
    [("R", "R1", "", "R1"), ("R", "VR1", "a", "R_VR1_a"), ("Q", "Q3", "", "Q3"),
     ("X", "U1", "", "X_U1"), ("V", "IN", "", "V_IN")],
)  # fmt: skip
def test_element_name(letter: str, ref: str, suffix: str, name: str) -> None:
    assert element_name(letter, ref, suffix) == name


def test_ac_needs_a_guitar(models: ModelLibrary, circuit: Builder) -> None:
    c = circuit().part("R1", "resistor", "a", "0", value="1k").build()
    with pytest.raises(NetlistError, match="Add a guitar input"):
        generate_netlist(c, models, Ac())
    generate_netlist(c, models, Op())  # DC needs no input


def test_wrong_model_kind(models: ModelLibrary, circuit: Builder) -> None:
    c = circuit().part("Q1", "bjt", "a", "b", "0", model="J201").build()
    with pytest.raises(NetlistError, match="J201, which is a jfet model, not a bjt"):
        generate_netlist(c, models, Op())


def test_doubler_diodes_must_be_plain_diodes(models: ModelLibrary, circuit: Builder) -> None:
    """A zener is a subcircuit (D-155): the pump's copy of D1 is a `D` line (D-226)."""
    c = circuit().rail("V+", 9.0).pump("U1", "V+", double="o", diode="1N4738A").build()
    with pytest.raises(NetlistError, match="D1 is a zener"):
        generate_netlist(c, models, Op())


def test_two_zeners_keep_their_own_inner_models(models: ModelLibrary, circuit: Builder) -> None:
    c = (
        circuit().rail("V+", 9.0)
        .part("D1", "diode", "0", "V+", model="1N4738A")
        .part("D2", "diode", "0", "V+", model="1N4739A")
        .build()
    )  # fmt: skip
    text = generate_netlist(c, models, Op()).text
    assert re.search(r"(?m)^x_d1 0 \S+ 1n4738a$", text, re.I)
    assert text.lower().count(".subckt 1n473") == 2


def test_measured_values_need_level_one_and_right_sign(
    models: ModelLibrary, circuit: Builder
) -> None:
    c = circuit().part("Q1", "jfet", "a", "b", "0", model="J201",
                       measured={"idss": 1e-3, "vp": 0.8}).build()  # fmt: skip
    with pytest.raises(NetlistError, match="pinch-off voltage is negative"):
        generate_netlist(c, models, Op())


def test_dc_sources_sit_beside_the_ideal_rails(models: ModelLibrary, circuit: Builder) -> None:
    """The rails are always ideal sources, and a DC source on a net of its own is always
    in (D-091): nothing is switched off any more."""
    built = (
        circuit()
        .rail("V+", 9.0)
        .part("V1", "vsource", "V16", "0", value=16)
        .part("R1", "resistor", "V16", "V+", value="10k")
        .build()
    )
    text = generate_netlist(built, models, Op()).text
    assert "V_RAIL1 v_ 0 DC 9" in text.splitlines()
    assert "V1 v16 0 DC 16" in text.splitlines()


def test_tran_save_must_exist(models: ModelLibrary, circuit: Builder) -> None:
    c = circuit().part("IN", "guitar", "a").part("R1", "resistor", "a", "0", value=1).build()
    with pytest.raises(NetlistError, match="no net 'nope' to record"):
        generate_netlist(c, models, Tran(200, 0.1, 0.01, 1e-5, save=("nope",)))


def test_dc_sweep_line_and_no_guitar_needed(models: ModelLibrary, circuit: Builder) -> None:
    c = (
        circuit("diode jig")
        .part("V1", "vsource", "a", "0", value=0)
        .part("D1", "diode", "a", "0", model="1N4148")
        .build()
    )
    lines = generate_netlist(c, models, Dc("V1", -1, 1, 0.01)).text.splitlines()
    assert lines[-2:] == [".dc V1 -1 1 0.01", ".end"]


def test_dc_sweep_needs_a_voltage_source(models: ModelLibrary, circuit: Builder) -> None:
    c = every_part(circuit).build()
    with pytest.raises(NetlistError, match="R1 isn't one"):
        generate_netlist(c, models, Dc("R1", 0, 1, 0.1))


def test_elements_are_the_netlist_lines(models: ModelLibrary, circuit: Builder) -> None:
    c = every_part(circuit).build()
    netlist = generate_netlist(c, models, Ac())
    lines = netlist.text.splitlines()
    assert all(" ".join(e.tokens) in lines for e in netlist.elements)
    by_name = {e.tokens[0]: e.ref for e in netlist.elements}
    assert by_name["R_VR1_a"] == "VR1" and by_name["R_VR1_b"] == "VR1"
    assert by_name["V_IN"] == "IN" and by_name["L_IN"] == "IN"  # the pickup's parts too
    assert by_name["X_U1"] == "U1"
    # every part has an element (the rail's has none); parts are emitted in file order
    assert {e.ref for e in netlist.elements} == {None} | {p.ref for p in c.parts}


def test_rail_sources_have_no_part(models: ModelLibrary, circuit: Builder) -> None:
    c = circuit().rail("V+", 9.0).part("R1", "resistor", "V+", "0", value="1k").build()
    [rail, r1] = generate_netlist(c, models, Op()).elements
    assert rail.ref is None and rail.tokens == ("V_RAIL1", "v_", "0", "DC", "9")
    assert r1.ref == "R1"


def test_part_elements_for_other_values(models: ModelLibrary, circuit: Builder) -> None:
    c = every_part(circuit).build()
    vr1 = c.part("VR1")
    steps = [vr1.model_copy(update={"rotation": r}) for r in (0.0, 0.5, 1.0)]
    out = part_elements(c, steps, models, Ac())
    values = [[float(e.tokens[3]) for e in step] for step in out]
    assert values == [[1.0, 100000.0], [10000.0, 90000.0], [100000.0, 1.0]]  # A taper
    assert all(e.tokens[1:3] == ("fb", "fb") for e in (s[0] for s in out))
    # the circuit's own netlist is untouched
    assert "R_VR1_a fb fb 5000" in generate_netlist(c, models, Ac()).text


def test_sensing_puts_a_source_in_series_with_each_semiconductor_pin(
    models: ModelLibrary, circuit: Builder
) -> None:
    c = every_part(circuit).build()
    netlist = generate_netlist(c, models, Ac(sense=True))
    lines = netlist.text.splitlines()
    assert "V_SQ2_C v_ s_q2_c DC 0" in lines
    assert "Q2 s_q2_c s_q2_b s_q2_e 2N5089" in lines
    # op-amp pins: + and - spelled p and m so V+ and V- stay apart; only the model's pins
    u1 = {s.pin: s for s in netlist.sensed["U1"]}
    assert list(u1) == ["+", "-", "V+", "V-", "out", "comp1", "comp2"]  # LM308's order
    assert (u1["V+"].source, u1["V-"].source) == ("V_SU1_Vp", "V_SU1_Vm")
    assert u1["+"].net == "b" and u1["V+"].node == "v_"
    assert {e.ref for e in netlist.elements if e.tokens[0] == "V_SU1_Vp"} == {"U1"}
    # without sensing nothing changes
    assert "V_S" not in generate_netlist(c, models, Ac()).text


def test_unused_comp_pins_are_not_sensed(models: ModelLibrary, circuit: Builder) -> None:
    c = (
        circuit()
        .rail("V+", 9.0)
        .part("IN", "guitar", "in")
        .part("U1", "opamp", "in", "o", "o", model="TL072")
        .part("OUT", "amp", "o")
        .build()
    )
    sensed = generate_netlist(c, models, Ac(sense=True)).sensed["U1"]
    assert [s.pin for s in sensed] == ["+", "-", "V+", "V-", "out"]


def test_injection_drives_a_net_and_quiets_the_guitar(
    models: ModelLibrary, circuit: Builder
) -> None:
    c = every_part(circuit).build()
    lines = generate_netlist(c, models, Ac(inject="o")).text.splitlines()
    assert "I_INJECT 0 o DC 0 AC 1" in lines
    assert "V_IN in_in_emf 0 DC 0 AC 0" in lines
    with pytest.raises(NetlistError, match="no net 'nowhere'"):
        generate_netlist(c, models, Ac(inject="nowhere"))


def test_the_guitar_or_amp_left_out(models: ModelLibrary, circuit: Builder) -> None:
    """D-127: an impedance looking in from an end: the part gone, 1 GΩ in its place."""
    c = every_part(circuit).build()
    lines = generate_netlist(c, models, Ac(inject="in", open="IN")).text.splitlines()
    assert "R_IN_open in 0 1000000000" in lines
    assert not any(line.startswith("V_IN") for line in lines)
    with pytest.raises(NetlistError, match="Only the guitar or the amp can be left out, not R1"):
        generate_netlist(c, models, Ac(inject="in", open="R1"))


def test_a_buffered_guitars_volume_turns_only_its_level(
    models: ModelLibrary, circuit: Builder
) -> None:
    """D-134: buffered, the volume pot sits before the buffer, so the source is stiff at the
    pot's divider ratio: a 500k B pot at 25 % is 125k over 500k, a quarter of the level,
    in a frequency run, a test tone and a recording; no pot elements."""
    c = (
        circuit()
        .part("IN", "guitar", "in", volume="500k", taper="B", rotation=0.25)
        .part("R1", "resistor", "in", "0", value="10k")
        .build()
    )
    ac = generate_netlist(c, models, Ac(10, 1e4, 10)).text
    assert re.search(r"^V_IN \S+ 0 DC 0 AC 0\.25$", ac, re.M)
    assert "R_IN_vola" not in ac
    tone = generate_netlist(c, models, Tran(200, 0.3, 0.01, 1e-5, ["in"])).text
    assert re.search(r"^V_IN \S+ 0 DC 0 SIN\(0 0\.075 200\)$", tone, re.M)
    played = Tran(200, 0.3, 0.01, 1e-5, ["in"], source_file="clip.txt", gain=2.0)
    assert "amplscale=[0.5]" in generate_netlist(c, models, played).text
    full = generate_netlist(c.with_part("IN", rotation=1.0), models, Ac(10, 1e4, 10))
    level = re.search(r"^V_IN \S+ 0 DC 0 AC (\S+)$", full.text, re.M)
    assert level and float(level[1]) == pytest.approx(1.0, abs=1e-5)  # the pot's end stop


def test_a_run_can_keep_only_its_end_and_start_from_a_state(
    circuit: Callable[..., CircuitBuilder], models: ModelLibrary
) -> None:
    """D-275: a wait keeps its last point; the run after it starts from every node's
    volts (.ic lines, `uic`) and each inductor's amps (its own `ic=`)."""
    c = (
        circuit()
        .part("IN", "guitar", "in")
        .part("L1", "inductor", "in", "out", value="100m")
        .part("R1", "resistor", "out", "0", value="10k")
        .build()
    )
    plain = generate_netlist(c, models, Tran(200, 0.3, 0.01, 1e-5)).text
    assert ".tran 1e-05 0.01 0 1e-05\n" in plain and "ic" not in plain.lower().split()
    wait = generate_netlist(c, models, Tran(200, 0.3, 0.01, 1e-5, keep_from=0.009995)).text
    assert ".tran 1e-05 0.01 0.009995 1e-05\n" in wait
    started = Tran(200, 0.3, 0.01, 1e-5, state=(("in", 0.25), ("out", -0.125)),
                   coil_amps=(("l1", 1.5e-05),))  # fmt: skip
    text = generate_netlist(c, models, started).text
    coil = next(ln for ln in text.splitlines() if ln.startswith("L1 "))
    assert coil.endswith(" 0.1 ic=1.5e-05")
    assert ".ic v(in)=0.25\n.ic v(out)=-0.125\n.tran 1e-05 0.01 0 1e-05 uic\n.end\n" in text
    assert [ln for ln in text.splitlines() if "ic=" in ln] == [coil]


def test_loose_parts_are_left_out(circuit: Builder, models: ModelLibrary) -> None:
    """D-165: a part no current reaches isn't in the netlist, and asking to record its
    net says why in plain English."""
    c = (
        circuit()
        .part("IN", "guitar", "in")
        .part("R1", "resistor", "in", "0", value="1M")
        .part("C9", "capacitor", "x", None, value="1n")
        .build()
    )
    text = generate_netlist(c, models, Op()).text
    assert "R1" in text and "C9" not in text
    with pytest.raises(NetlistError, match="C9 isn't wired into the circuit yet"):
        generate_netlist(c, models, Tran(200, 0.1, 0.01, 1e-4, save=("x",)))


def test_a_pump_wired_as_both_doubles_and_inverts_with_one_input(
    models: ModelLibrary, circuit: Builder
) -> None:
    """D-218, D-226: one chip, its pump cap and diodes doubling, its flying cap inverting on
    VOUT; the input draws for both, and the drawn parts are ordinary parts."""
    c = (
        circuit().rail("V+", 9.0)
        .pump("U1", "V+", double="o", invert="n", model="LT1054", diode="1N4001")
        .part("R1", "resistor", "o", "0", value="18k")
        .part("R2", "resistor", "n", "0", value="9k")
    ).build()  # fmt: skip
    text = generate_netlist(c, models, Op()).text
    lines = [ln.split()[0].lower() for ln in text.splitlines() if ln[:1] in "BbDdCc"]
    assert sorted(x for x in lines if "u1" in x) == ["b_u1_dbl", "b_u1_in", "b_u1_out", "d_u1_1"]
    assert {"c1", "c2", "d1", "d2"} <= set(lines)


def test_a_pump_missing_a_part_says_what(models: ModelLibrary, circuit: Builder) -> None:
    """D-226: a pump with its parts missing doesn't pump, as a real chip wouldn't."""
    alone = circuit().rail("V+", 9.0).part("U1", "chargepump", "V+", "0", "0", model="TC1044S")
    with pytest.raises(NetlistError, match="U1 pumps nothing yet: draw a flying cap"):
        generate_netlist(alone.part("R1", "resistor", "V+", "0", value="1k").build(), models, Op())
    half = (
        circuit().rail("V+", 9.0)
        .part("U1", "chargepump", "V+", "0", "0", "cp", model="TC1044S")
        .part("C1", "capacitor", "j", "cp", value="10u")
        .part("D1", "diode", "V+", "j", model="1N5817")
        .part("R1", "resistor", "j", "0", value="1k")
    ).build()  # fmt: skip
    with pytest.raises(NetlistError, match="needs a diode from C1 to its output"):
        generate_netlist(half, models, Op())
    grounded = circuit().rail("V+", 9.0).pump("U1", "V+", invert="0")
    with pytest.raises(NetlistError, match="flying cap C1 pumps into ground"):
        generate_netlist(grounded.build(), models, Op())


def test_pump_resistance_swaps_the_sheets_cap_for_the_drawn_one(models: ModelLibrary) -> None:
    """D-226: R = sheet's - 1/(f C_sheet) + 1/(f C_drawn). TC1044S: 60 ohms with 10 uF at
    5 kHz, so 1 uF gives 60 - 20 + 200; LT1054: 10 ohms with 100 uF at 25 kHz, so 10 uF
    gives 10 - 0.4 + 4."""

    def cap(value: str) -> Capacitor:
        return Capacitor(ref="C1", type="capacitor", pos=(0, 0), value=value)

    tc = ChargePump(ref="U1", type="chargepump", pos=(0, 0), model="TC1044S")
    lt = ChargePump(ref="U1", type="chargepump", pos=(0, 0), model="LT1054")
    assert pump_resistance(tc, cap("10u"), models) == pytest.approx(60.0)
    assert pump_resistance(tc, cap("1u"), models) == pytest.approx(240.0)
    assert pump_resistance(lt, cap("10u"), models) == pytest.approx(13.6)


def test_a_pump_without_ripple_runs_at_its_average(models: ModelLibrary, circuit: Builder) -> None:
    """A render with pump switching off (TODO 2026-11-09): no switching term, and no step
    cap from the pump's frequency (the LT1054's 25 kHz x 20 steps is 2 µs); on, both."""
    c = (
        circuit().rail("V+", 9.0)
        .part("IN", "guitar", "in")
        .part("R9", "resistor", "in", "0", value="1M")
        .pump("U1", "V+", double="o", model="LT1054", diode="1N4001")
        .part("R1", "resistor", "o", "0", value="18k")
    ).build()  # fmt: skip
    played = Tran(0, 0, 0.01, 1 / 96000, ("in",), source_file="clip.txt")
    on = generate_netlist(c, models, played).text
    off = generate_netlist(c, models, replace(played, pump_ripple=False)).text
    assert "tanh" in on and re.search(r"^\.tran 2e-0?6 ", on, re.M)
    assert "tanh" not in off
    step = re.search(r"^\.tran (\S+) ", off, re.M)
    assert step and float(step[1]) == pytest.approx(1 / 96000, rel=1e-3)


def test_an_led_resistor_named_ledr_is_still_a_resistor_to_spice() -> None:
    """D-232: SPICE reads an element by its first letter, so LEDR1 (an L) goes out as
    R_LEDR1; RPD1 already starts with R."""
    from solum.netlist import element_name

    assert element_name("R", "LEDR1") == "R_LEDR1"
    assert element_name("R", "RPD1") == "RPD1"
