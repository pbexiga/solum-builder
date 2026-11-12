from pathlib import Path

import pytest

from solum.yamlio import YamlError, load_yaml


def test_reads_plain_yaml(tmp_path: Path) -> None:
    f = tmp_path / "a.yaml"
    f.write_text("source: https://example.org\nchecks:\n  - {node: OUT, expected: 4.5}\n")
    assert load_yaml(f) == {"source": "https://example.org",
                            "checks": [{"node": "OUT", "expected": 4.5}]}  # fmt: skip


def test_refuses_python_object_tags(tmp_path: Path) -> None:
    f = tmp_path / "evil.yaml"
    f.write_text("x: !!python/object/apply:os.system ['true']\n")
    with pytest.raises(YamlError, match="isn't valid YAML"):
        load_yaml(f)


def test_missing_and_broken(tmp_path: Path) -> None:
    with pytest.raises(YamlError, match="Couldn't read"):
        load_yaml(tmp_path / "none.yaml")
    f = tmp_path / "bad.yaml"
    f.write_text("a: [1, 2\n")
    with pytest.raises(YamlError, match=r"line \d"):
        load_yaml(f)
