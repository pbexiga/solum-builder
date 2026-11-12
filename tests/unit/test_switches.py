"""Switch types and their poles (D-143): the type table, the v13 → v14 migration, and
which contacts close."""

from pathlib import Path

import pytest

from solum.circuit.connectivity import connect
from solum.circuit.io import load_circuit
from solum.circuit.parts import closed_contacts, pin_positions
from solum.circuit.schema import SCHEMA_VERSION, Switch
from solum.circuit.switches import KINDS, catalogue, from_poles_throws, kind_of

OLD = Path(__file__).parents[1] / "fixtures" / "circuits" / "old" / "schema-v13.json"
OLD_V14 = OLD.with_name("schema-v14.json")


def test_every_kind_is_consistent() -> None:
    for kind in KINDS.values():
        assert len(kind.closed) == len(kind.positions) >= 2, kind.id
        for closed in kind.closed:
            assert len(closed) == kind.poles, kind.id
            assert all(lug is None or lug in kind.throws for lug in closed), kind.id
    assert {k["id"] for k in catalogue()} == set(KINDS)


def test_the_set_the_user_picked() -> None:
    """Toggles on-on and on-off-on, the on-on-on 3-way, rotaries 1P/2P 3-6T, the stomp."""
    for kind in ("spst", "spdt", "spdt-on-off-on", "dpdt", "dpdt-on-off-on", "dpdt-on-on-on",
                 "3pdt", "3pdt-on-off-on", "rotary-1p3t", "rotary-2p6t", "footswitch"):  # fmt: skip
        assert kind in KINDS
    assert kind_of("dpdt-on-off-on").positions == ("1", "Off", "2")
    assert kind_of("footswitch").positions == ("On", "Bypassed")


def test_on_on_on_middle_is_honeywells() -> None:
    """2NT1-12: centre joins A2-A3 and B2-B1."""
    a = Switch(ref="SW1A", type="switch", kind="dpdt-on-on-on", pole="a", position=1)
    b = Switch(ref="SW1B", type="switch", kind="dpdt-on-on-on", pole="b", position=1)
    assert closed_contacts(a) == [("A2", "A3")]
    assert closed_contacts(b) == [("B2", "B1")]


def test_centre_off_opens_the_pole() -> None:
    sw = Switch(ref="SW1", type="switch", kind="spdt-on-off-on", position=1)
    assert closed_contacts(sw) == []
    assert closed_contacts(sw.model_copy(update={"position": 2})) == [("2", "3")]


@pytest.mark.parametrize(
    ("old", "new"),
    [((1, 1, 0), ("spst", 0)), ((1, 2, 1), ("spdt", 1)), ((2, 2, 0), ("dpdt", 0)),
     ((3, 1, 1), ("3pdt", 0)), ((3, 1, 0), ("3pdt", 1)), ((2, 4, 3), ("rotary-2p4t", 3))],
)  # fmt: skip
def test_v13_poles_and_throws_become_a_type(
    old: tuple[int, int, int], new: tuple[str, int]
) -> None:
    assert from_poles_throws(*old) == new


def test_no_type_for_a_three_pole_rotary() -> None:
    with pytest.raises(ValueError, match="no switch type"):
        from_poles_throws(3, 4, 0)


def test_v13_file_loads_with_its_switches_as_poles() -> None:
    """Each pole where it was drawn (60 apart, turned with the part), lugs where the old
    pins were, so wires still meet; probes, targets and notes follow."""
    c = load_circuit(OLD)
    a, b = c.part("SW1A"), c.part("SW1B")
    assert isinstance(a, Switch) and isinstance(b, Switch)
    assert (a.kind, a.position, a.label, a.pole) == ("rotary-2p3t", 2, "Clip", "a")
    # 60 down, turned 90°: 60 left; then v15 moves a rotary 20 down (left) so its
    # throws stay where they were
    assert b.pole == "b" and b.pos == (20, 40)
    assert pin_positions(b)["B3"] == (0, 60)  # where v13's 2T3 was
    spst, spdt = c.part("SW2"), c.part("SW3")
    assert isinstance(spst, Switch) and (spst.kind, spst.position) == ("spst", 1)
    assert isinstance(spdt, Switch) and spdt.kind == "spdt"
    assert c.probes.in_ == "SW1A.AC" and c.probes.out == "SW3.3"
    trimmer = c.part("TR1")
    assert getattr(trimmer, "bias_target").node == "SW1B.B3"  # noqa: B009
    assert [(p.ref, p.note) for p in c.parts if p.note] == [("SW1A", "the clipping selector")]


def test_a_switchs_name_sets_every_pole(repo: Path) -> None:
    c = load_circuit(repo / "library" / "starters" / "tone-bender-mk2-mode.json")
    flipped = c.with_part("SW1", position=1)
    assert [getattr(flipped.part(r), "position") for r in ("SW1A", "SW1B")] == [1, 1]  # noqa: B009


def test_throws_sit_as_kicad_draws_them() -> None:
    """v15 (D-143): an SPDT's throws a step above and below its common (KiCad's SW_SPDT),
    an SP3T's above, level and below; more, 20 apart and centred."""
    spdt = Switch(ref="SW1", type="switch", kind="spdt")
    assert pin_positions(spdt) == {"2": (-20, 0), "1": (20, -20), "3": (20, 20)}
    rotary = Switch(ref="SW1", type="switch", kind="rotary-1p4t")
    assert [pin_positions(rotary)[lug] for lug in ("1", "2", "3", "4")] == [
        (20, -30), (20, -10), (20, 10), (20, 30)
    ]  # fmt: skip
    assert pin_positions(Switch(ref="SW1", type="switch", kind="spst"))["2"] == (20, 0)


def test_v14_switches_keep_their_wiring() -> None:
    """A v14 file's switches, redrawn as v15 draws them, are wired as they were: a wire
    from an SPDT's new lug 1 to where it was, a rotary moved down with a wire from its
    common to where that was. An unwired one gets no wire."""
    c = load_circuit(OLD_V14)
    nets = connect(c)
    wired = {
        ("SW1", "2"): "c", ("SW1", "1"): "a", ("SW1", "3"): "b",
        ("SW2", "C"): "rc", ("SW2", "1"): "r1", ("SW2", "2"): "r2", ("SW2", "3"): "r3",
    }  # fmt: skip
    assert {pin: nets.net_of(*pin) for pin in wired} == wired
    assert c.part("SW2").pos == (100, 320)  # type: ignore[union-attr]
    assert c.part("SW3").pos == (300, 100)  # type: ignore[union-attr]
    assert nets.net_of("SW4", "1") == nets.net_of("R1", "1")  # a pin on the lug, no wire
    assert len(c.wires) == 7 + 3  # SW1's and SW4's lug 1, SW2's common


def test_a_v21_file_loads_as_v22() -> None:
    """v22 (9c) only adds a custom switch's own contacts: a v21 file's switches are as they
    were."""
    c = load_circuit(OLD.with_name("schema-v21.json"))
    sw = c.part("SW1")
    assert isinstance(sw, Switch) and (sw.kind, sw.custom, sw.position) == ("spdt", None, 0)
    assert c.schema_ == SCHEMA_VERSION


def test_the_types_pedals_use_most_come_first() -> None:
    """9c (the user): the on-on, on-off-on and on-on-on toggles first, then the momentary
    toggles; then on-off, push buttons, footswitches (DPDT, 3PDT, momentary) and Alpha's
    rotaries. Only what's sold ("trim to what's sold")."""
    ids = list(KINDS)
    assert ids[:10] == ["spdt", "dpdt", "3pdt", "4pdt", "spdt-on-off-on", "dpdt-on-off-on",
                        "3pdt-on-off-on", "dpdt-on-on-on",
                        "spdt-momentary", "dpdt-momentary"]  # fmt: skip
    assert ids[10:17] == ["spst", "dpst", "push-no", "push-nc", "footswitch-dpdt", "footswitch",
                          "footswitch-momentary"]  # fmt: skip
    assert ids[17:19] == ["dip-2", "dip-3"]  # D-238
    rotaries = [i.removeprefix("rotary-") for i in ids[19:]]
    assert rotaries == ["1p3t", "1p4t", "1p5t", "1p6t", "1p12t",
                        "2p3t", "2p4t", "2p5t", "2p6t", "3p4t", "4p3t"]  # fmt: skip


def test_a_momentary_toggle_rests_off_and_springs_back() -> None:
    """(on)-off-(on): an on-off-on whose ends spring back; Knobs holds where it's put."""
    sw = Switch(ref="SW1A", type="switch", kind="dpdt-momentary", pole="a")
    kind = sw.switch_kind
    assert (kind.short, kind.positions) == ("DPDT (on)-off-(on)", ("1", "Off", "2"))
    assert kind.closed == (("1", "1"), (None, None), ("3", "3"))
    assert "springs back to Off" in kind.hint
    assert KINDS["spdt-momentary"].name == "SPDT (on)-off-(on) toggle (momentary)"


def test_a_push_button_joins_or_opens_while_pressed() -> None:
    no = Switch(ref="SW1", type="switch", kind="push-no")
    nc = Switch(ref="SW2", type="switch", kind="push-nc")
    assert no.switch_kind.positions == ("Released", "Pressed")
    assert closed_contacts(no) == [] and closed_contacts(nc) == [("1", "2")]
    pressed = {"position": 1}
    assert closed_contacts(no.model_copy(update=pressed)) == [("1", "2")]
    assert closed_contacts(nc.model_copy(update=pressed)) == []


def test_only_selectors_are_drawn_as_rotaries() -> None:
    looks = {k.id: k.look for k in KINDS.values()}
    assert looks["rotary-1p12t"] == looks["rotary-2p3t"] == "rotary"
    assert looks["dpdt-on-on-on"] == looks["footswitch"] == looks["push-no"] == "toggle"


def custom(**over: object) -> dict[str, object]:
    """A 3-way custom DPDT: the other on-on-on middle (A2-A1 and B2-B3)."""
    return {
        "name": "3-way",
        "throws": 2,
        "positions": [
            {"name": "Up", "joins": [1, 1]},
            {"name": "Mid", "joins": [1, 2]},
            {"name": "Down", "joins": [2, 2]},
        ],
    } | over


def test_a_custom_switch_is_its_own_type() -> None:
    """9c: its poles, positions and contacts from its definition; a 2-throw toggle's lugs
    are 2 (common), 1, 3, as the built-in toggles'."""
    a = Switch(ref="SW1A", type="switch", kind="custom", pole="a", position=1, custom=custom())
    b = a.model_copy(update={"ref": "SW1B", "pole": "b"})
    assert a.switch_kind.poles == 2 and a.position_names == ["Up", "Mid", "Down"]
    assert pin_positions(a) == {"A2": (-20, 0), "A1": (20, -20), "A3": (20, 20)}
    assert closed_contacts(a) == [("A2", "A1")] and closed_contacts(b) == [("B2", "B3")]


def test_a_custom_rotarys_lugs_are_c_and_numbers() -> None:
    rotary = custom(
        name="Clip",
        throws=3,
        look="rotary",
        positions=[{"name": n, "joins": [j]} for n, j in (("Si", 1), ("Off", None), ("LED", 3))],
    )
    sw = Switch(ref="SW1", type="switch", kind="custom", position=2, custom=rotary)
    assert sw.switch_kind.lugs == ("C", "1", "2", "3") and sw.switch_kind.look == "rotary"
    assert closed_contacts(sw) == [("C", "3")]
    assert closed_contacts(sw.model_copy(update={"position": 1})) == []


@pytest.mark.parametrize(
    ("over", "message"),
    [
        ({"throws": 13}, "less than or equal to 12"),
        ({"positions": [{"name": "Only", "joins": [1]}]}, "at least 2"),
        ({"positions": [{"name": "A", "joins": [1]}, {"name": "B", "joins": [1, 2]}]}, "each of"),
        (
            {"positions": [{"name": "A", "joins": [3]}, {"name": "B", "joins": [1]}]},
            "throws 1 to 2",
        ),
        ({"look": "rotary"}, "3 throws or more"),
        (
            {"positions": [{"name": "A", "joins": [1] * 5}, {"name": "B", "joins": [1] * 5}]},
            "at most 4",
        ),
    ],
)
def test_a_custom_switch_keeps_to_its_limits(over: dict[str, object], message: str) -> None:
    with pytest.raises(ValueError, match=message):
        Switch(ref="SW1", type="switch", kind="custom", custom=custom(**over))


def test_custom_contacts_only_on_a_custom_switch() -> None:
    with pytest.raises(ValueError, match="needs its contacts"):
        Switch(ref="SW1", type="switch", kind="custom")
    with pytest.raises(ValueError, match="needs its contacts"):
        Switch(ref="SW1", type="switch", kind="spdt", custom=custom())


def test_a_dip_switch_has_a_position_for_every_combination() -> None:
    """D-238: a DIP's switches are independent, so as one switch of N poles its positions
    are every on/off combination (switch 1 is the lowest bit), on the board, not a knob."""
    two = kind_of("dip-2")
    assert (two.group, two.short, two.lugs) == ("DIP", "DIP-2", ("1", "2"))
    assert two.positions == ("All off", "1 on", "2 on", "1 and 2 on")
    assert two.closed == ((None, None), ("2", None), (None, "2"), ("2", "2"))
    assert len(kind_of("dip-3").positions) == 8 and kind_of("dip-3").positions[5] == "1 and 3 on"
    a = Switch(ref="SW1A", type="switch", kind="dip-2", pole="a", position=2)
    b = Switch(ref="SW1B", type="switch", kind="dip-2", pole="b", position=2)
    assert closed_contacts(a) == [] and closed_contacts(b) == [("B1", "B2")]
