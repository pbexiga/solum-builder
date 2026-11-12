"""Load, validate and save circuit files. The only code that reads or writes them."""

import json
import os
import tempfile
from collections.abc import Mapping
from pathlib import Path
from typing import Any

from pydantic import ValidationError

from solum.circuit.migrations import MigrationError, migrate
from solum.circuit.schema import Circuit


class CircuitError(ValueError):
    """A circuit file is unreadable or invalid. `str(err)` says what and where."""


def parse_circuit(data: Mapping[str, Any]) -> Circuit:
    """Validate (after migrating to the current schema) a circuit given as a dict."""
    try:
        return Circuit.model_validate(migrate(data))
    except MigrationError as err:
        raise CircuitError(str(err)) from None
    except ValidationError as err:
        raise CircuitError(describe_errors(err, data)) from None


def describe_errors(err: ValidationError, data: Mapping[str, Any]) -> str:
    """One plain line per problem, naming the part by ref where there is one."""
    lines = []
    for e in err.errors():
        where = _location(e["loc"], data)
        message = e["msg"].removeprefix("Value error, ")
        lines.append(f"{where}: {message}" if where else message)
    return "This circuit file has problems:\n- " + "\n- ".join(lines)


def _location(loc: tuple[int | str, ...], data: Mapping[str, Any]) -> str:
    parts = list(loc)
    if len(parts) >= 2 and parts[0] == "parts" and isinstance(parts[1], int):
        part_list = data.get("parts", [])
        ref = part_list[parts[1]].get("ref") if parts[1] < len(part_list) else None
        # Drop the union tag pydantic inserts (e.g. "resistor") after the index.
        rest = [str(p) for p in parts[3:]] if len(parts) > 2 else []
        name = f"part {ref}" if isinstance(ref, str) else f"part #{parts[1] + 1}"
        return " ".join([name, *rest]) if rest else name
    return ".".join(str(p) for p in parts)


def load_circuit(path: Path) -> Circuit:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except OSError as err:
        raise CircuitError(f"Couldn't read {path}: {err.strerror}.") from None
    except json.JSONDecodeError as err:
        raise CircuitError(f"{path} isn't valid JSON (line {err.lineno}): {err.msg}.") from None
    if not isinstance(data, dict):
        raise CircuitError(f"{path} doesn't hold a circuit (expected a JSON object).")
    return parse_circuit(data)


def circuit_to_dict(circuit: Circuit) -> dict[str, Any]:
    """The file form: aliases (`from`, `in`, `schema`), defaults left out, except the
    schema and the version tag, which every file shows."""
    data = circuit.model_dump(mode="json", by_alias=True, exclude_defaults=True)
    data.pop("version", None)
    return {"schema": circuit.schema_, "id": data.pop("id"), "name": data.pop("name"),
            "version": circuit.version.model_dump(), **data}  # fmt: skip


def circuit_to_json(circuit: Circuit) -> str:
    return json.dumps(circuit_to_dict(circuit), indent=2, ensure_ascii=False) + "\n"


def save_circuit(circuit: Circuit, path: Path) -> None:
    """Write atomically (temp file + rename) so a crash never leaves half a file."""
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=path.parent, prefix=f".{path.name}.", suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            f.write(circuit_to_json(circuit))
        os.replace(tmp, path)
    except BaseException:
        Path(tmp).unlink(missing_ok=True)
        raise
