"""The plain-English pieces shared by the app's sentences."""

from solum.words import listed


def test_listed_joins_with_commas_and_a_last_and() -> None:
    assert listed([]) == ""
    assert listed(["R1"]) == "R1"
    assert listed(["R1", "C2"]) == "R1 and C2"
    assert listed(["R1", "C2", "C3"]) == "R1, C2 and C3"
