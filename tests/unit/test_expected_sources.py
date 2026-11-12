"""The expected-values files' sources (D-292): a source that may not be used commercially
is cited and said in our words, never quoted."""

from pathlib import Path

from tests.acceptance.expected import load_expected


def test_a_non_commercial_source_is_never_quoted(repo: Path) -> None:
    files = sorted((repo / "tests" / "fixtures" / "acceptance").glob("*.expected.yaml"))
    non_commercial = [f for f in files if "BY-NC" in load_expected(f).source.licence]
    assert len(non_commercial) >= 9  # ElectroSmash's analyses
    for path in non_commercial:
        expected = load_expected(path)
        quoted = [c.id for c in expected.checks if c.quote]
        assert not quoted, f"{path.name}: say these in our own words (`says`): {quoted}"
        assert "short quotes" not in expected.source.licence, path.name
