"""The one YAML reader (D-033): always `yaml.safe_load`, never object construction."""

from pathlib import Path
from typing import Any

import yaml


class YamlError(ValueError):
    """A YAML file couldn't be read (plain-English message)."""


def load_yaml(path: Path) -> Any:
    try:
        return yaml.safe_load(path.read_text(encoding="utf-8"))
    except OSError as err:
        raise YamlError(f"Couldn't read {path}: {err.strerror}.") from None
    except yaml.YAMLError as err:
        mark = getattr(err, "problem_mark", None)
        where = f" (line {mark.line + 1})" if mark is not None else ""
        raise YamlError(f"{path} isn't valid YAML{where}.") from None
