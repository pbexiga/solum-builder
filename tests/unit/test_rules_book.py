"""Rule files: loading, validation, text filling and the check registry (no ngspice)."""

from pathlib import Path

import pytest

from solum.circuit.build import CircuitBuilder
from solum.models import load_models
from solum.rules.checks import CHECKS, Context, cap_rating_advice, listing
from solum.rules.rule import RuleBook, RuleError, load_rule, load_rules
from solum.rules.run import Checker, check_book, rule_book

LIBRARY = Path(__file__).resolve().parents[2] / "library"
RULE = """\
id: {id}
layer: topology
severity: warning
check: part_shorted
title: Part shorted
message: "{{ref}} is shorted."
why: Because.
fix: "Fix {{ref}}."
fixtures:
  bad: [{{parts: []}}]
  good: [{{parts: []}}]
"""


def write(tmp: Path, name: str, text: str) -> Path:
    path = tmp / f"{name}.yaml"
    path.write_text(text, encoding="utf-8")
    return path


def test_the_app_rule_book_loads_and_matches_the_checks() -> None:
    book = rule_book(LIBRARY)
    assert len(book.rules) >= 35
    assert {r.check for r in book.rules} == set(CHECKS)
    assert [r.id for r in book.rules] == sorted(r.id for r in book.rules)


def test_a_rule_fills_its_texts(tmp_path: Path) -> None:
    rule = load_rule(write(tmp_path, "shorted", RULE.format(id="shorted")))
    assert rule.fields() == {"ref"}
    assert rule.text("message", {"ref": "R1"}) == "R1 is shorted."


def test_the_file_name_must_match_the_id(tmp_path: Path) -> None:
    with pytest.raises(RuleError, match=r"must be named other\.yaml"):
        load_rule(write(tmp_path, "wrong", RULE.format(id="other")))


def test_bad_rules_are_refused_plainly(tmp_path: Path) -> None:
    with pytest.raises(RuleError, match="should hold one rule"):
        load_rule(write(tmp_path, "x", "- a\n- b\n"))
    with pytest.raises(RuleError, match="isn't valid YAML"):
        load_rule(write(tmp_path, "y", "id: [\n"))
    text = RULE.format(id="z").replace("layer: topology", "layer: later")
    with pytest.raises(RuleError, match="layer"):
        load_rule(write(tmp_path, "z", text))
    stop = RULE.format(id="w").replace("layer: topology", "layer: operating_point")
    with pytest.raises(RuleError, match="only topology rules can stop"):
        load_rule(write(tmp_path, "w", stop + "stops_sim: true\n"))


def test_a_rule_must_name_a_check_of_its_layer(tmp_path: Path) -> None:
    write(tmp_path, "a", RULE.format(id="a").replace("part_shorted", "nothing_like_it"))
    with pytest.raises(RuleError, match="doesn't exist"):
        check_book(load_rules(tmp_path))
    (tmp_path / "a.yaml").unlink()
    write(tmp_path, "b", RULE.format(id="b").replace("part_shorted", "bjt_saturated"))
    with pytest.raises(RuleError, match="operating_point check"):
        check_book(load_rules(tmp_path))


def test_listing_names_a_few_then_counts() -> None:
    assert listing(["a"]) == "a"
    assert listing(["a", "b"]) == "a and b"
    assert listing(["a", "b", "c", "d", "e"]) == "a, b, c and 2 more"


def test_contradictory_wiring_only_reports_the_wiring() -> None:
    spec = {"parts": [{"ref": "R1", "type": "resistor", "nets": ["a", "GND"], "value": "1k"}],
            "labels": [{"net": "b", "pos": [80, 100]}]}  # fmt: skip
    c = CircuitBuilder.from_spec(spec).build()
    checker = Checker(rule_book(LIBRARY), load_models([LIBRARY / "models"]))
    found = checker.topology(c)
    assert [p.rule for p in found] == ["labels-joined"]
    assert found[0].message == "Net labels a and b are wired together."


def test_topology_checks_on_a_hand_built_circuit() -> None:
    c = (
        CircuitBuilder()
        .rail("V+", 9)
        .part("R1", "resistor", "a", "a", value="1k")
        .part("R2", "resistor", "a", "GND", value="1k")
        .part("D1", "diode", "V+", "GND", model="1N4148")
        .build()
    )
    checker = Checker(rule_book(LIBRARY), load_models([LIBRARY / "models"]))
    found = {(p.rule, p.refs) for p in checker.topology(c)}
    assert ("part-shorted", ("R1",)) in found
    assert ("diode-across-supply", ("D1",)) in found
    assert checker.stoppers(c) == []  # neither stops a simulation


def test_the_context_needs_consistent_wiring() -> None:
    ctx = Context(CircuitBuilder().build(), load_models([LIBRARY / "models"]), None)
    with pytest.raises(AssertionError):
        _ = ctx.n


def test_rule_book_lookup() -> None:
    book = RuleBook(())
    with pytest.raises(KeyError):
        book.get("missing")


def test_build_checks_group_their_parts_and_say_they_are_build_checks() -> None:
    c = (
        CircuitBuilder()
        .rail("V+", 9)
        .part("R1", "resistor", "V+", "a", value="10k")
        .part("C10", "capacitor", "a", "GND", value="1u")
        .part("C2", "capacitor", "a", "GND", value="100n")
        .part("C1", "capacitor", "a", "GND", value="100u", kind="electrolytic")
        .build()
    )
    checker = Checker(rule_book(LIBRARY), load_models([LIBRARY / "models"]))
    found = {p.rule: p for p in checker.topology(c)}
    no_kind = found["cap-no-kind"]
    assert no_kind.refs == ("C2", "C10")  # in parts-list order, one problem for both
    assert no_kind.message.startswith("C2 and C10 have no type")
    assert no_kind.build and no_kind.severity == "info"
    rating = found["cap-no-rating"]
    assert rating.refs == ("C1",)
    assert rating.fix == "Give each a voltage rating in its form: 16 V or more here."
    book = rule_book(LIBRARY)
    assert {r.id for r in book.rules if r.build} >= {
        "cap-no-kind", "cap-no-rating", "cap-rating-close", "cap-over-voltage",
        "resistor-power-close", "resistor-over-power", "part-no-package", "switch-custom",
        "part-not-simulated",
    }  # fmt: skip


@pytest.mark.parametrize(
    ("volts", "advice"),
    [(5.0, "6.3 V or more"), (9.0, "16 V or more"), (12.0, "16 V or more"),
     (12.9, "25 V or more"), (18.0, "25 V or more"), (90.0, "one rated well above 90 V")],
)  # fmt: skip
def test_cap_rating_advice_leaves_a_fifth_spare(volts: float, advice: str) -> None:
    assert cap_rating_advice(volts) == advice
