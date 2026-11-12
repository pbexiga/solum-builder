import json
from pathlib import Path

import pytest

from solum import bench, cli
from solum.sim.native import NativeNgspice


def test_bench_circuit_is_biased_and_amplifies(engine: NativeNgspice, repo: Path) -> None:
    circuit = (repo / "library" / "bench" / "big-muff.cir").read_text()
    report = bench.run_bench(engine, circuit, runs=1, audio_runs=0)
    results = report["results"]
    # Every collector sits mid-rail on 9 V, so no stage is saturated or cut off.
    for node, volts in results["op"]["check"].items():
        assert 2.0 < volts < 7.0, node
    assert results["ac"]["check"]["peak_gain_db"] > 30
    assert results["tran_50ms"]["check"]["points"] > 5000


@pytest.mark.timing  # a speed check: run on its own (make accept)
def test_cli_bench_prints_json(
    capsys: pytest.CaptureFixture[str], tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("CACHE_DIR", str(tmp_path / "cache"))
    assert cli.main(["bench", "--runs", "1", "--audio-runs", "0", "--knob-runs", "2"]) == 0
    report = json.loads(capsys.readouterr().out)
    assert report["engine"] == "native"
    results = report["results"]
    assert set(results) == {"op", "ac", "tran_50ms", "knob_turn", "cache", "find_parts"}
    assert results["knob_turn"]["max_s"] < 1.0  # Phase 2: Tone in under a second
    # Phase 10: the cache where it lives (a call that syncs to disk, D-126, is ~10 ms),
    # and Find parts through it; asked again, every result is read back
    assert results["cache"]["calls"] == 200
    assert results["cache"]["put_ms"] < 5 and results["cache"]["get_ms"] < 5
    assert results["find_parts"]["first_s"] < 5.0
    assert results["find_parts"]["again_s"] < results["find_parts"]["first_s"] / 2
    assert report["cache_dir"] == str(tmp_path / "cache")
    assert not (tmp_path / "cache" / "bench").exists()  # its own folder, removed


def test_cli_run_prints_op_ac_and_tran(
    capsys: pytest.CaptureFixture[str], repo: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("CACHE_DIR", str(tmp_path))
    monkeypatch.setenv("DATA_DIR", str(tmp_path / "data"))
    circuit = str(repo / "tests" / "fixtures" / "circuits" / "jfet-drive.json")
    assert (
        cli.main(["run", circuit, "--op", "--ac", "OUT", "--tran", "Q1.D", "--level", "hard"]) == 0
    )
    out = capsys.readouterr().out
    assert "DC operating point" in out
    assert "Bias: TR1 solved to" in out
    assert "Frequency response at OUT" in out
    assert "Waveform at Q1.D, hard input (1 V peak, 200 Hz)" in out
    assert cli.main(["run", circuit, "--ac", "OUT", "--json"]) == 0
    data = json.loads(capsys.readouterr().out)
    assert data["ac"][0]["valid"] is True


def test_cli_run_reports_plain_errors(
    capsys: pytest.CaptureFixture[str], repo: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("CACHE_DIR", str(tmp_path))
    circuit = str(repo / "tests" / "fixtures" / "circuits" / "jfet-drive.json")
    assert cli.main(["run", circuit, "--ac", "NOPE"]) == 1
    assert "There's no net or pin called 'NOPE'" in capsys.readouterr().err
    assert cli.main(["run", str(tmp_path / "missing.json")]) == 1
    assert "Couldn't read" in capsys.readouterr().err
