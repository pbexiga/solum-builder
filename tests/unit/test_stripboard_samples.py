"""Published stripboard layouts entered by hand (P8 R2, D-410, D-412): each passes our check with
no faults and only the warnings its fixture lists, so the editor can draw what builders
draw. Each fixture (`tests/fixtures/stripboard/*-tagboard.yaml`) names its starter, the
drawing it was read from and how it differs from our starter; `circuit` holds the drawing's
own parts where they differ (a part it leaves out, a model, an op-amp half, a capacitor's
kind), applied to the starter before the check."""

from pathlib import Path
from typing import Any

import pytest

from solum.circuit.io import circuit_to_dict, load_circuit, parse_circuit
from solum.circuit.schema import Circuit, Stripboard
from solum.guides import footprint_table
from solum.models import load_models
from solum.stripboard.board import layout_data, layout_from_data
from solum.stripboard.check import check_layout, progress
from solum.yamlio import load_yaml

REPO = Path(__file__).resolve().parents[2]
LIBRARY = REPO / "library"
MODELS = load_models([LIBRARY / "models"])
TABLE = footprint_table(LIBRARY)
SAMPLES = sorted((REPO / "tests" / "fixtures" / "stripboard").glob("*-tagboard.yaml"))


def as_drawn(data: dict[str, Any]) -> Circuit:
    """The fixture's starter with the drawing's own parts (`circuit`) and the board's
    on/off choices (`where` is read from the circuit's board, D-385), read back as a
    saved file is, so it's a circuit the app would open. A stage moved to the chip's other
    half (`half`) takes that half's ref (IC1A on half B is IC1B: the file's rule)."""
    circuit = load_circuit(LIBRARY / "starters" / f"{data['starter']}.json")
    edits = data.get("circuit", {})
    parts = []
    for part in circuit.parts:
        if part.ref in edits.get("omit", ()):
            continue
        for field in ("model", "half", "kind"):
            if part.ref in edits.get(field, {}):
                part = part.model_copy(update={field: edits[field][part.ref]})
        if part.ref in edits.get("half", {}):
            part = part.model_copy(update={"ref": part.ref[:-1] + edits["half"][part.ref].upper()})
        parts.append(part)
    board = Stripboard.model_validate(layout_data(layout_from_data(data)))
    drawn = circuit.model_copy(update={"parts": parts, "stripboard": board})
    return parse_circuit(circuit_to_dict(drawn))


def test_there_are_the_four_sample_boards() -> None:
    assert [p.name for p in SAMPLES] == [
        "klon-centaur-tagboard.yaml",
        "marshall-bluesbreaker-tagboard.yaml",
        "proco-rat-tagboard.yaml",
        "ts808-tagboard.yaml",
    ]


@pytest.mark.parametrize("path", SAMPLES, ids=lambda p: p.stem)
def test_a_published_board_passes_the_check_with_its_warnings(path: Path) -> None:
    data = load_yaml(path)
    circuit, layout = as_drawn(data), layout_from_data(data)
    assert check_layout(layout, circuit, MODELS, TABLE).faults == []
    now = progress(layout, circuit, MODELS, TABLE)
    assert now.done and now.faults == [] and now.to_place == []
    assert now.warnings + [o.text for o in now.overlaps] == data["warnings"]


@pytest.mark.parametrize("path", SAMPLES, ids=lambda p: p.stem)
def test_a_sample_board_is_the_drawing_its_acceptance_file_counts(path: Path) -> None:
    """The fixture is the drawing as printed: its size, cuts and links, which are also the
    starter's published benchmark (`stripboard:` in its acceptance file, D-391)."""
    data = load_yaml(path)
    drawing = data["drawing"]
    expected = load_yaml(REPO / "tests/fixtures/acceptance" / f"{data['starter']}.expected.yaml")
    bench = expected["stripboard"]
    assert drawing["url"] == bench["url"]
    assert drawing["size"] == [bench["columns"], bench["strips"]] == data["size"]
    assert drawing["cuts"] == bench["cuts"] == len(data["cuts"])
    assert drawing["links"] == bench["links"] == len(data["links"])
