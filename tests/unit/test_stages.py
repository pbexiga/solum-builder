"""The Bias & headroom pane's pure parts (Phase 8c, D-106): finding stages and clippers
in signal order, and the measures, checked by hand."""

import math
from collections.abc import Callable
from pathlib import Path

import pytest

from solum.circuit.build import CircuitBuilder
from solum.circuit.connectivity import connect
from solum.circuit.io import load_circuit
from solum.stages import (
    Clips,
    bias_position,
    centring_rank,
    clipper_clips,
    device_room,
    discrete_opamps,
    drive_db,
    first_to_clip,
    harmonic_lead,
    headroom_db,
    pot_places,
    signal_input,
    signal_stages,
    stage_clips,
    stage_parts,
)
from solum.view import rail_nets

Builder = Callable[..., CircuitBuilder]
STARTERS = Path(__file__).resolve().parents[2] / "library" / "starters"


def rows(name: str) -> list[tuple[str, str]]:
    c = load_circuit(STARTERS / f"{name}.json")
    return [(s.label, s.role) for s in signal_stages(c, connect(c))]


def test_the_ts808_in_signal_order() -> None:
    # the drive op-amp, its diodes in feedback right after it, then the tone op-amp
    assert rows("ts808") == [
        ("Q1", "buffer"),
        ("IC1B", "op-amp stage"),
        ("D1, D2", "in feedback"),
        ("IC1A", "op-amp stage"),
        ("Q3", "buffer"),
    ]


def test_the_big_muff_in_signal_order() -> None:
    # this starter numbers from the output end: Q4 is the input booster; each clipping
    # stage's diodes reach its base through a 1 µF cap, and still count as feedback
    assert rows("big-muff-pi-v3") == [
        ("Q4", "gain stage"),
        ("Q3", "gain stage"),
        ("D3, D4", "in feedback"),
        ("Q2", "gain stage"),
        ("D1, D2", "in feedback"),
        ("Q1", "gain stage"),
    ]


def test_the_rat_and_the_fuzz_face() -> None:
    assert rows("proco-rat") == [
        ("IC1", "op-amp stage"),
        ("D1, D2", "to ground"),
        ("Q1", "buffer"),
    ]
    assert rows("fuzz-face") == [("Q1", "gain stage"), ("Q2", "gain stage")]


def test_diodes_that_arent_clippers_are_left_out(circuit: Builder) -> None:
    c = (
        circuit("not clippers")
        .rail("V+", 9.0)
        .part("IN", "guitar", "in")
        .part("R1", "resistor", "in", "x", value="1k")
        # series chains each way to ground: one clipper, its four diodes together
        .part("D1", "diode", "x", "m1", model="1N4148")
        .part("D2", "diode", "m1", "0", model="1N4148")
        .part("D3", "diode", "0", "m2", model="1N4148")
        .part("D4", "diode", "m2", "x", model="1N4148")
        # a polarity diode on the supply and an indicator off the signal path
        .part("D5", "diode", "V+", "0", model="1N4148")
        .part("R2", "resistor", "V+", "led", value="4k7")
        .part("D6", "diode", "led", "0", model="1N4148")
        .part("OUT", "amp", "x")
        .build()
    )
    found = signal_stages(c, connect(c))
    assert [(s.label, s.role, s.net) for s in found] == [("D1, D2, D3, D4", "to ground", "x")]


def test_a_stages_parts_are_what_touches_its_pins(circuit: Builder) -> None:
    """D-122: the device, then every part on one of its pins' nets but the supply and
    ground; a coupling cap between two stages is in both."""
    c = (
        circuit("two stages")
        .rail("V+", 9.0)
        .part("IN", "guitar", "in")
        .part("C1", "capacitor", "in", "b1", value="100n")
        .part("R11", "resistor", "V+", "b1", value="1M")
        .part("Q1", "bjt", "c1", "b1", "0", model="2N3904")
        .part("R12", "resistor", "V+", "c1", value="10k")
        .part("C2", "capacitor", "c1", "b2", value="100n")
        .part("R21", "resistor", "V+", "b2", value="1M")
        .part("Q2", "bjt", "c2", "b2", "0", model="2N3904")
        .part("R22", "resistor", "V+", "c2", value="10k")
        .part("OUT", "amp", "c2")
        .build()
    )
    nets = connect(c)
    assert stage_parts(c, nets, ["Q1"]) == ["Q1", "C1", "R11", "R12", "C2"]
    assert stage_parts(c, nets, ["Q2"]) == ["Q2", "C2", "R21", "R22"]  # not the amp


VOICE_LUGS = {"2": "e", "1": "lo", "3": "hi"}


def two_voices(circuit: Builder, position: int) -> list[str]:
    """A boost whose SPDT picks its emitter leg: lug 1 the Clean leg, lug 3 the Hot."""
    c = (
        circuit("two voices")
        .rail("V+", 9.0)
        .part("IN", "guitar", "in")
        .part("C1", "capacitor", "in", "b", value="100n")
        .part("R1", "resistor", "V+", "b", value="1M")
        .part("Q1", "bjt", "c", "b", "e", model="2N3904")
        .part("R2", "resistor", "V+", "c", value="10k")
        .part(
            "SW1", "switch", kind="spdt", position=position, pins={"2": "e", "1": "lo", "3": "hi"}
        )
        .part("R3", "resistor", "lo", "0", value="2k2")  # Clean
        .part("R4", "resistor", "hi", "0", value="390")  # Hot
        .part("C3", "capacitor", "hi", "0", value="22u")
        .part("OUT", "amp", "c")
        .build()
    )
    return stage_parts(c, connect(c), ["Q1"])


def test_a_stage_lights_the_voice_its_switch_picks(circuit: Builder) -> None:
    """9c, two voices: a closed contact joins its nets, so the leg the switch picks is the
    stage's and lights with it; the other leg's parts don't."""
    assert two_voices(circuit, 0) == ["Q1", "C1", "R1", "R2", "SW1", "R3"]
    assert two_voices(circuit, 1) == ["Q1", "C1", "R1", "R2", "SW1", "R4", "C3"]


def chips(name: str) -> list[tuple[str, str, str]]:
    """Each pot's chip on a starter: (ref, where, the block it's on or the row it follows)."""
    c = load_circuit(STARTERS / f"{name}.json")
    nets = connect(c)
    found = signal_stages(c, nets)
    labels = ["guitar", *(s.label for s in found)]
    return [
        (p.ref, p.at, labels[p.index + 1] if p.at != "end" else "")
        for p in pot_places(c, nets, found)
    ]


def test_where_the_starters_pots_act() -> None:
    """D-122: on a block (its inputs or its feedback), on the arrow after the row before
    it, or at the end. Every starter's guitar has its volume (D-136): first, at the input."""
    guitar = ("IN", "arrow", "guitar")
    assert chips("proco-rat") == [
        guitar,
        ("VR1", "block", "IC1"),  # in its feedback
        ("VR2", "arrow", "IC1"),  # the Filter: at the diodes' node, so before them
        ("VR3", "end", ""),
    ]
    assert chips("ts808") == [
        guitar,
        ("VR1", "block", "IC1B"),  # Drive: in series with the feedback resistor
        ("VR2", "block", "IC1A"),  # Tone: on its inputs (an active tone stage)
        ("VR3", "arrow", "IC1A"),  # Level: before the output buffer
    ]
    assert chips("big-muff-pi-v3") == [
        guitar,
        ("VR1", "arrow", "Q4"),  # into Q3
        ("VR2", "arrow", "D1, D2"),  # between Q2 (and its diodes) and Q1
        ("VR3", "end", ""),
    ]
    assert chips("fuzz-face") == [guitar, ("VR1", "block", "Q2"), ("VR2", "end", "")]


def test_a_pot_before_the_first_stage_and_one_off_the_path(circuit: Builder) -> None:
    c = (
        circuit("input pot")
        .rail("V+", 9.0)
        .part("IN", "guitar", "in")
        .part("VR1", "pot", "in", "w", "0", value="100k")  # an input level
        .part("C1", "capacitor", "w", "b", value="100n")
        .part("R31", "resistor", "V+", "b", value="1M")
        .part("Q1", "bjt", "c", "b", "0", model="2N3904")
        .part("R32", "resistor", "V+", "c", value="10k")
        .part("VR2", "pot", "V+", "x", "0", value="10k")  # a bias divider nothing plays through
        .part("OUT", "amp", "c")
        .build()
    )
    nets = connect(c)
    places = pot_places(c, nets, signal_stages(c, nets))
    assert [(p.ref, p.at, p.index) for p in places] == [("VR1", "arrow", -1), ("VR2", "end", -1)]


def test_no_guitar_no_stages(circuit: Builder) -> None:
    c = circuit("no input").part("R1", "resistor", "a", "0", value="1k").build()
    assert signal_stages(c, connect(c)) == []


def test_a_common_emitters_room() -> None:
    # collector at 6 V, emitter at 1 V, on 9 V: 3 V up to the rail, 5 - 0.3 down
    assert device_room(6.0, 1.0, 0.3, "n", False, [0.0, 9.0]) == pytest.approx((3.0, 4.7))
    # a pnp mirrors it: the device limits upward swings at its collector
    assert device_room(-6.0, -1.0, 0.3, "p", False, [-9.0, 0.0]) == pytest.approx((4.7, 3.0))


def test_a_followers_room() -> None:
    # emitter at 4 V, collector on 9 V: up until Vce reaches 0.3 V, down to ground
    assert device_room(9.0, 4.0, 0.3, "n", True, [0.0, 9.0]) == pytest.approx((4.7, 4.0))


def test_bias_position() -> None:
    assert bias_position(4.0, 4.0) == (0.5, "centred")
    assert bias_position(2.0, 8.0) == (pytest.approx(0.8), "sits high")
    assert bias_position(7.0, 3.0) == (pytest.approx(0.3), "sits low")
    assert bias_position(math.inf, 3.0) == (0.0, "sits low")  # no rail above it


def test_headroom_and_drive_by_hand() -> None:
    assert headroom_db(2.0, 3.0, 1.0) == pytest.approx(6.0206)  # the side with less room
    assert headroom_db(2.0, 3.0, 4.0) == pytest.approx(-6.0206)  # over by 6 dB
    assert headroom_db(2.0, 3.0, 0.0) is None
    assert drive_db(2.0, 1.0) == pytest.approx(6.0206)  # 6 dB taken off
    assert drive_db(1.0, 2.0) == 0.0  # nothing taken off
    assert stage_clips(-0.5, held=False) and not stage_clips(-0.5, held=True)
    assert not stage_clips(None, held=False) and not stage_clips(3.0, held=False)
    assert clipper_clips(1.0) and not clipper_clips(0.9)


def test_which_harmonics_lead() -> None:
    assert harmonic_lead({2: -10, 3: -30, 4: -40, 5: -40, 6: -50, 7: -50, 8: -60}) == "even"
    assert harmonic_lead({2: -40, 3: -12, 4: -50, 5: -20, 6: -60, 7: -30, 8: -70}) == "odd"
    assert harmonic_lead({2: -20, 3: -21, 4: -40, 5: -40, 6: -50, 7: -50, 8: -60}) == "both"


def test_the_first_to_clip() -> None:
    found = [
        Clips("Q1", "buffer", frozenset()),
        Clips("U1", "op-amp stage", frozenset({"hard"})),
        Clips("D1, D2", "clipper", frozenset({"med", "hard"})),
    ]
    levels = ["soft", "med", "hard"]
    # the lowest level first, then the earliest in the signal
    assert first_to_clip(found, levels) == "Clips first: D1, D2 (clipper), from a medium pick."
    assert first_to_clip(found[:2], levels) == ("Clips first: U1 (op-amp stage), from a hard pick.")
    assert first_to_clip(found[:1], levels) == "Nothing clips, even at a hard pick."


def test_bias_to_ranks_by_its_own_aim() -> None:
    """D-123: asked for 30 %, a change that lands there beats one that centres it."""
    assert centring_rank(0.3, 2.0, 0, 0.3) < centring_rank(0.5, 1.1, 0, 0.3)


def test_centring_ranks_centred_then_fewest_moved_then_smallest_change() -> None:
    """D-119: a change that centres beats one that doesn't; then one that pushes no other
    stage off centre; then the smaller change, either way (x2 and /2 tie)."""
    centred_big = centring_rank(0.5, 4.0, 0)
    centred_small = centring_rank(0.55, 1.2, 0)
    moves_one = centring_rank(0.5, 1.1, 1)
    off = centring_rank(0.75, 1.01, 0)
    assert sorted([off, moves_one, centred_big, centred_small]) == [
        centred_small,
        centred_big,
        moves_one,
        off,
    ]
    assert centring_rank(0.5, 2.0, 0) == pytest.approx(centring_rank(0.5, 0.5, 0))


def test_where_the_signal_enters_a_row() -> None:
    """D-123: a transistor's base or gate, an op-amp's + input, a clipper to ground's own
    node; a clipper in feedback has none."""
    c = load_circuit(STARTERS / "ts808.json")
    nets = connect(c)
    rows = {s.label: s for s in signal_stages(c, nets)}
    assert signal_input(c, nets, rows["Q1"]) == nets.net_of("Q1", "B")
    assert signal_input(c, nets, rows["IC1B"]) == nets.net_of("IC1B", "+")
    assert signal_input(c, nets, rows["D1, D2"]) is None
    rat = load_circuit(STARTERS / "proco-rat.json")
    rat_nets = connect(rat)
    clipper = next(s for s in signal_stages(rat, rat_nets) if s.kind == "clipper")
    assert signal_input(rat, rat_nets, clipper) == clipper.net


def test_a_mosfet_is_a_gain_stage_or_a_follower(circuit: Builder) -> None:
    """D-176: a MOSFET's rows are a JFET's: the drain is the output, or the source when the
    drain sits on a supply."""
    c = (
        circuit("mosfets")
        .rail("V+", 9.0)
        .part("IN", "guitar", "in")
        .part("Q1", "mosfet", "d", "in", "0", model="2N7000")
        .part("R1", "resistor", "V+", "d", value="10k")
        .part("Q2", "mosfet", "V+", "d", "s", model="2N7000")
        .part("R2", "resistor", "s", "0", value="10k")
        .part("OUT", "amp", "s")
        .build()
    )
    found = signal_stages(c, connect(c))
    assert [(s.label, s.role, s.net) for s in found] == [
        ("Q1", "gain stage", "d"),
        ("Q2", "buffer", "s"),
    ]
    assert signal_input(c, connect(c), found[1]) == "d"


def test_the_bd2s_discrete_op_amps_are_one_stage_each() -> None:
    """D-224: Q2/Q3 (a JFET pair) with Q4, and Q5/Q6 with Q7, are each one stage, named
    in signal order (+ input, - input, output) and measured from the + input."""
    assert rows("boss-bd2-aion")[:4] == [
        ("Q1", "buffer"),  # IC1A buffers VB, a bias net: not a stage
        ("Q2, Q3, Q4", "discrete op-amp"),
        ("D2, D3, D4, D5", "to ground"),
        ("Q5, Q6, Q7", "discrete op-amp"),
    ]
    c = load_circuit(STARTERS / "boss-bd2-aion.json")
    nets = connect(c)
    first = next(s for s in signal_stages(c, nets) if s.refs[0] == "Q4")
    assert first.inputs == ("Q2.G", "Q3.G") and first.net == "Q4.C"
    assert signal_input(c, nets, first) == "Q2.G"
    bd2 = chips("boss-bd2-aion")  # Drive: a gang in each one's feedback; Bass on IC1B, not IC1A
    assert ("VR1", "block", "Q2, Q3, Q4") in bd2 and ("VR1", "block", "Q5, Q6, Q7") in bd2
    assert ("VR4", "block", "IC1B") in bd2


def pair_and_output(circuit: Builder, feedback: bool = True, tail: str = "s") -> CircuitBuilder:
    """A JFET pair (tail R3 to ground) whose Q1 drain drives a PNP, its collector fed
    back to Q2's gate by R5 when `feedback`."""
    b = (
        circuit().rail("V+", 9.0)
        .part("IN", "guitar", "in")
        .part("Q1", "jfet", "d1", "in", tail, model="J201")
        .part("Q2", "jfet", "V+", "m", tail, model="J201")
        .part("R1", "resistor", "V+", "d1", value="10k")
        .part("R3", "resistor", "s", "0", value="4k7")
        .part("Q3", "bjt", "out", "d1", "V+", model="2N3906")
        .part("R4", "resistor", "out", "0", value="10k")
        .part("R6", "resistor", "m", "0", value="1k")
    )  # fmt: skip
    return b.part("R5", "resistor", "out", "m", value="22k") if feedback else b


def test_a_pair_and_an_output_stage_with_feedback_is_an_op_amp(circuit: Builder) -> None:
    """D-224: found with its feedback; without it, three transistors as they are."""
    for feedback, want in ((True, [("Q3", "Q1", "Q2")]), (False, [])):
        c = pair_and_output(circuit, feedback).build()
        nets = connect(c)
        assert [d.refs for d in discrete_opamps(c, nets, rail_nets(c, nets))] == want
    c = pair_and_output(circuit).build()
    (only,) = [s for s in signal_stages(c, connect(c)) if s.kind == "stage"]
    assert (only.label, only.net) == ("Q1, Q2, Q3", "out")


def test_a_pair_with_its_tail_on_ground_is_not_a_pair(circuit: Builder) -> None:
    """D-224: two sources on ground share a net, but a supply isn't a pair's tail."""
    c = pair_and_output(circuit, tail="0").build()
    nets = connect(c)
    assert discrete_opamps(c, nets, rail_nets(c, nets)) == []
