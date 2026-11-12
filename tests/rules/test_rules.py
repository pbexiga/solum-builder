"""Every rule against its own fixtures: it fires on each `bad` circuit (on the parts named
in `expect`, if any) and stays quiet on each `good` one (D-013, D-077)."""

import pytest

from solum.rules.checks import CHECKS
from solum.rules.rule import RuleBook
from solum.rules.run import Checker, rule_book
from solum.simulate import Simulator
from tests.rules.conftest import LIBRARY, fixture_problems

BOOK = rule_book(LIBRARY)
CASES = [
    pytest.param(rule.id, kind, i, id=f"{rule.id}-{kind}{i}")
    for rule in BOOK.rules
    for kind in ("bad", "good")
    for i in range(len(getattr(rule.fixtures, kind)))
]


@pytest.mark.parametrize(("rule_id", "kind", "index"), CASES)
def test_rule_fixture(
    rule_id: str, kind: str, index: int, checker: Checker, sim: Simulator
) -> None:
    rule = BOOK.get(rule_id)
    spec = getattr(rule.fixtures, kind)[index]
    found = [p for p in fixture_problems(spec, checker, sim) if p.rule == rule_id]
    if kind == "good":
        assert not found, f"{rule_id} fired on a good fixture: {[p.message for p in found]}"
        return
    assert found, f"{rule_id} didn't fire on bad fixture {index}"
    for ref in spec.get("expect", []):
        assert any(ref in p.refs for p in found), f"{rule_id} didn't name {ref}"
    for p in found:  # every text filled in, nothing left in braces
        for text in (p.title, p.message, p.why, p.fix):
            assert "{" not in text and text.strip()


def test_every_check_has_a_rule(book: RuleBook) -> None:
    assert sorted(CHECKS) == sorted(r.check for r in book.rules)


def test_target_size_of_the_rule_book(book: RuleBook) -> None:
    # SPEC §4: about 35-40 for v1; Phase 8 power rules (D-093); part-not-simulated (D-165);
    # the build checks (D-203); model-missing (D-288)
    assert 35 <= len(book.rules) <= 66
