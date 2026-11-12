"""The exported netlists (D-206) run in plain ngspice, the program a builder has, and give
the operating point the app simulates: every starter, every analysis."""

import io
import re
import shutil
import subprocess
import zipfile
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from solum.api.app import create_app
from solum.circuit.io import load_circuit
from solum.config import load_settings
from solum.export import export_netlists, model_files, models_list
from solum.models import load_models
from solum.netlist import Op, generate_netlist
from solum.sim.native import NativeNgspice
from solum.simulate import Simulator

pytestmark = [
    pytest.mark.sim,
    pytest.mark.skipif(shutil.which("ngspice") is None, reason="needs the ngspice program"),
]
LIBRARY = Path(__file__).resolve().parents[2] / "library"
MODELS = load_models([LIBRARY / "models"])
STARTERS = sorted((LIBRARY / "starters").glob("*.json"))


def ngspice(path: Path) -> str:
    done = subprocess.run(["ngspice", "-b", str(path)], capture_output=True, text=True, timeout=120)
    out = done.stdout + done.stderr
    assert done.returncode == 0, out[-2000:]
    assert not re.search(r"^\s*error", out, re.I | re.M), out[-2000:]
    return out


@pytest.mark.parametrize("path", STARTERS, ids=lambda p: p.stem)
def test_each_netlist_runs_in_plain_ngspice(
    path: Path, engine: NativeNgspice, tmp_path: Path
) -> None:
    sim = Simulator(engine, MODELS)
    circuit = load_circuit(path)
    files = export_netlists(circuit, sim)
    assert [f.name for f in files] == ["op.cir", "ac.cir", "tran.cir"]
    for f in files:
        assert f.text.startswith(f"* {circuit.name}: ")
        assert ".control" not in f.text and f.text.rstrip().endswith(".end")
        (tmp_path / f.name).write_text(f.text)
    printed = ngspice(tmp_path / "op.cir")
    # the app's own operating point, trimmers solved, at every net ngspice printed
    op = sim.op(circuit)
    nodes = dict(re.findall(r"^\s+([a-z0-9_]+)\s+(-?[0-9.]+e[-+][0-9]+)\s*$", printed, re.M))
    biased = sim.solve_bias(circuit).circuit
    named = generate_netlist(biased, sim.models, Op()).nodes
    netlist_nodes = {net: node for net, node in named.items() if node in nodes}
    assert len(netlist_nodes) >= 5
    for net, node in netlist_nodes.items():
        assert float(nodes[node]) == pytest.approx(op.voltages[net], abs=2e-3), net
    for name in ("ac.cir", "tran.cir"):
        rows = re.findall(r"^\d+\t", ngspice(tmp_path / name), re.M)
        assert len(rows) > 100, name  # the .print table came out


def test_the_models_list_names_every_model_and_its_file() -> None:
    circuit = load_circuit(LIBRARY / "starters" / "proco-rat.json")
    text = models_list(circuit, MODELS)
    files = {f.name for f in model_files(circuit, MODELS)}
    assert files == {"models/1N4148.lib", "models/2N5458.lib", "models/LM308.lib"}
    for model in ("1N4148 (diode, model)", "2N5458 (jfet, model)", "LM308 (opamp, subckt)"):
        assert model in text
    assert "pins, in order: A K" in text and "pins, in order: D G S" in text
    lm308 = text.split("LM308 (opamp, subckt)")[1]
    assert "pins, in order: " in lm308 and "file: models/LM308.lib" in lm308


def test_the_netlists_download_as_one_zip(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("DATA_DIR", str(tmp_path / "data"))
    monkeypatch.setenv("CACHE_DIR", str(tmp_path / "cache"))
    client = TestClient(create_app(load_settings()))
    got = client.get("/api/export/starter/fuzz-face/netlists.zip")
    assert got.status_code == 200 and "netlists.zip" in got.headers["content-disposition"]
    names = sorted(zipfile.ZipFile(io.BytesIO(got.content)).namelist())
    assert names == ["ac.cir", "models.txt", "models/AC128.lib", "op.cir", "tran.cir"]
