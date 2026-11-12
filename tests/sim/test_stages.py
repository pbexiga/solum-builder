"""The Bias & headroom pane through real ngspice (Phase 8c, D-106)."""

import json
import math
from pathlib import Path
from typing import Any

import numpy as np
import pytest
from fastapi.testclient import TestClient

from solum.api.app import create_app
from solum.circuit.connectivity import connect
from solum.circuit.io import circuit_to_dict, load_circuit, parse_circuit
from solum.config import load_settings
from solum.fixes import (
    Arranged,
    FixError,
    bias_options,
    bias_reach,
    clipper_options,
    gain_options,
)
from solum.models import load_models
from solum.probe import stage_levels, stage_waves, stages_view
from solum.sim.native import NativeNgspice
from solum.simulate import Simulator
from solum.units import parse_value, snap_to_series
from tests.sim.test_probe import Builder, common_emitter

pytestmark = pytest.mark.sim
REPO = Path(__file__).resolve().parents[2]


@pytest.fixture(scope="module")
def sim(engine: NativeNgspice) -> Simulator:
    return Simulator(engine, load_models([REPO / "library" / "models"]))


def starter(name: str) -> Any:
    return load_circuit(REPO / "library" / "starters" / f"{name}.json")


def test_a_common_emitters_bias_and_headroom_by_hand(sim: Simulator, circuit: Builder) -> None:
    c = common_emitter(circuit).build()
    view = stages_view(sim, c)
    (row,) = view["rows"]
    assert (row["label"], row["role"], row["net"]) == ("Q1", "gain stage", "c")
    op = sim.op(c).voltages
    bias = row["bias"]
    # the room is the DC: up to the 9 V rail, down until Vce is 0.3 V
    assert bias["v"] == pytest.approx(op["c"])
    assert bias["up"] == pytest.approx(9.0 - op["c"])
    assert bias["down"] == pytest.approx(op["c"] - op["e"] - 0.3)
    soft = row["levels"]["soft"]
    # clean at a soft pick: the unclipped prediction is what the transient reaches
    peak = max(soft["up"], soft["down"])
    assert 20 * math.log10(soft["predicted"] / peak) == pytest.approx(0.0, abs=0.5)
    room = min(bias["up"], bias["down"])
    assert row["limit"] == pytest.approx(room)
    assert soft["headroom_db"] == pytest.approx(20 * math.log10(room / soft["predicted"]))
    # a harder pick has less room left
    levels = row["levels"]
    assert (
        levels["soft"]["headroom_db"] > levels["med"]["headroom_db"] > levels["hard"]["headroom_db"]
    )


def test_the_ts808s_clipper_is_driven_harder_at_each_pick(sim: Simulator) -> None:
    view = stages_view(sim, starter("ts808"))
    by = {r["label"]: r for r in view["rows"]}
    drive = [by["D1, D2"]["levels"][lv]["drive_db"] for lv in ("soft", "med", "hard")]
    assert drive[0] < drive[1] < drive[2]
    assert drive[0] >= 1.0  # clipping from a soft pick
    # the drive op-amp's output is held by its diodes: never "over"
    assert all(cell["held"] for cell in by["IC1B"]["levels"].values())
    assert view["summary"] == "Clips first: D1, D2 (clipper), from a soft pick."
    # across the diodes it clamps where a silicon pair conducts, the same each way
    clamp = by["D1, D2"]["clamp"]
    assert 0.4 < clamp["up"] < 0.8 and clamp["down"] == pytest.approx(clamp["up"], rel=0.05)
    assert (
        clamp["short"].startswith("±")
        and clamp["text"] == f"Clamps at {clamp['short']} across it (hard pick)."
    )
    assert by["D1, D2"]["limit"] is None  # in feedback: the clamp is across it, not at u2o


def test_the_ts808_drives_its_diodes_harder_at_1k_than_at_100_hz(sim: Simulator) -> None:
    """D-122: headroom and drive at the test tones. The TS808's drive op-amp has 4.7k
    and 47 nF to ground in its feedback (a 720 Hz corner), so it has far less gain at
    100 Hz than at 1 kHz, and its diodes are driven less there."""
    low, high = (stages_view(sim, starter("ts808"), tone) for tone in (100.0, 1000.0))
    assert (low["tone"], high["tone"]) == (100.0, 1000.0)
    assert low["settled"] is True and high["settled"] is True
    u2 = next(r for r in high["rows"] if r["label"] == "IC1B")
    assert set(u2["gain_db"]) == {"100", "200", "1000", "3000"}
    assert u2["gain_db"]["1000"] > u2["gain_db"]["100"] + 6
    # the gains don't depend on the tone the view was asked for (one AC sweep)
    assert next(r for r in low["rows"] if r["label"] == "IC1B")["gain_db"] == u2["gain_db"]

    def drive(view: dict[str, Any]) -> float:
        row = next(r for r in view["rows"] if r["label"] == "D1, D2")
        return float(row["levels"]["med"]["drive_db"])

    assert drive(high) > drive(low) + 3


def test_the_fuzz_face_has_no_clipper(sim: Simulator) -> None:
    view = stages_view(sim, starter("fuzz-face"))
    assert [r["kind"] for r in view["rows"]] == ["stage", "stage"]
    assert view["summary"].startswith("Clips first: ")


def test_a_search_asked_again_is_reused(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """D-127: Find parts' answer is kept by the request, so asking again for the same
    circuit and stage doesn't search again (after Discard, or coming back to a stage);
    any change to the circuit (a knob turned) is a new search. Asked for its progress,
    a kept answer comes back as the result line."""
    import solum.api.app as api

    runs: list[str] = []

    def counted(s: Simulator, c: Any, ref: str, **kw: Any) -> dict[str, Any]:
        runs.append(ref)
        return gain_options(s, c, ref, **kw)

    monkeypatch.setattr(api, "gain_options", counted)
    settings = load_settings({"DATA_DIR": str(tmp_path / "data"),
                              "CACHE_DIR": str(tmp_path / "cache"),
                              "LIBRARY_DIR": str(REPO / "library")})  # fmt: skip
    client = TestClient(create_app(settings))
    rat = circuit_to_dict(starter("proco-rat"))
    first = client.post("/api/stages/gain", json={"circuit": rat, "ref": "IC1"}).json()
    again = client.post("/api/stages/gain", json={"circuit": rat, "ref": "IC1", "progress": True})
    assert runs == ["IC1"]
    assert json.loads(again.text.splitlines()[-1])["result"] == first
    turned = circuit_to_dict(starter("proco-rat").with_part("VR1", rotation=0.2))
    client.post("/api/stages/gain", json={"circuit": turned, "ref": "IC1"})
    assert runs == ["IC1", "IC1"]


def test_the_endpoint(tmp_path: Path) -> None:
    settings = load_settings({"DATA_DIR": str(tmp_path / "data"),
                              "CACHE_DIR": str(tmp_path / "cache"),
                              "LIBRARY_DIR": str(REPO / "library")})  # fmt: skip
    client = TestClient(create_app(settings))
    body = client.post("/api/stages", json={"circuit": circuit_to_dict(starter("proco-rat"))})
    assert body.status_code == 200
    rows = body.json()["rows"]
    assert [r["label"] for r in rows] == ["IC1", "D1, D2", "Q1"]
    pots = [(p["name"], p["at"], p["index"]) for p in body.json()["pots"]]
    assert pots == [
        ("Guitar volume", "arrow", -1),
        ("Distortion", "block", 0),
        ("Filter", "arrow", 0),
        ("Volume", "end", -1),
    ]
    assert rows[0]["bias"]["limits"] == "datasheet"  # the LM308 records its swing (D-150)
    clamp = rows[1]["clamp"]  # to ground: the node stops where the diodes clamp
    assert rows[1]["limit"] == pytest.approx(max(clamp["up"], clamp["down"]))
    empty = client.post("/api/stages", json={"circuit": {**circuit_to_dict(starter("ts808")),
                                                         "parts": []}})  # fmt: skip
    assert empty.json()["note"] == "Add a guitar input to see the stages."
    level = client.post("/api/stages/level", json={"circuit": circuit_to_dict(starter("proco-rat")),
                                                   "amplitude": 0.5})  # fmt: skip
    assert [r["net"] for r in level.json()["rows"]] == [r["net"] for r in rows]
    bad = client.post("/api/stages/level", json={"circuit": circuit_to_dict(starter("proco-rat")),
                                                 "amplitude": 0})  # fmt: skip
    assert bad.status_code == 422 and "above 0 V" in bad.json()["message"]
    rat = circuit_to_dict(starter("proco-rat"))
    high = client.post("/api/stages", json={"circuit": rat, "tone": 3000})
    assert high.status_code == 200 and high.json()["tone"] == 3000
    odd = client.post("/api/stages", json={"circuit": rat, "tone": 500})
    assert odd.status_code == 422
    assert odd.json()["message"] == "Pick one of the test tones: 100, 200, 1000, 3000 Hz."
    odd = client.post("/api/stages/level", json={"circuit": rat, "amplitude": 0.5, "tone": 500})
    assert odd.status_code == 422
    muff = circuit_to_dict(starter("big-muff-pi-v3"))
    centre = client.post("/api/stages/bias", json={"circuit": muff, "ref": "Q4"})
    assert centre.status_code == 200 and centre.json()["options"]
    low = client.post("/api/stages/bias", json={"circuit": muff, "ref": "Q4", "target": 0.3})
    assert low.status_code == 200 and low.json()["target"] == 0.3
    off = client.post("/api/stages/bias", json={"circuit": muff, "ref": "Q4", "target": 1.5})
    assert off.status_code == 422
    wrong = client.post("/api/stages/bias", json={"circuit": muff, "ref": "R1"})
    assert wrong.status_code == 422 and "isn't a stage" in wrong.json()["message"]
    gain = client.post("/api/stages/gain", json={"circuit": muff, "ref": "Q4"})
    assert gain.status_code == 200 and gain.json()["parts"][0]["steps"]
    # asked for its progress (D-123): a line per step, then the result (asked first:
    # asked again it's kept, D-127, and comes back at once)
    stepped = client.post(
        "/api/stages/clipper", json={"circuit": muff, "ref": "D3", "progress": True}
    )
    assert stepped.headers["content-type"] == "application/x-ndjson"
    lines = [json.loads(x) for x in stepped.text.splitlines()]
    assert [x["done"] for x in lines[:-1]] == [0, 1, 2, 3, 4] and lines[0]["of"] == 4
    assert len(lines[-1]["result"]["options"]) == 4
    swaps = client.post("/api/stages/clipper", json={"circuit": muff, "ref": "D3"})
    assert swaps.status_code == 200 and len(swaps.json()["options"]) == 4
    reach = client.post("/api/stages/reach", json={"circuit": muff, "ref": "Q4"})
    assert reach.status_code == 200 and reach.json()["lo"] < reach.json()["hi"]
    # the pane's own measuring too (D-127): the small-signal pass, then each pick
    tone = client.post("/api/stages", json={"circuit": muff, "tone": 1000, "progress": True})
    lines = [json.loads(x) for x in tone.text.splitlines()]
    assert [(x["done"], x["of"]) for x in lines[:-1]] == [(0, 4), (1, 4), (2, 4), (3, 4), (4, 4)]
    assert lines[-1]["result"]["tone"] == 1000 and lines[-1]["result"]["rows"]
    gone = client.post("/api/stages/gain", json={"circuit": muff, "ref": "R1", "progress": True})
    assert gone.status_code == 422 and "isn't a stage" in gone.json()["message"]
    # an arrangement the browser placed (D-124) comes back measured, under its key
    rat = circuit_to_dict(starter("proco-rat"))
    placed = {
        "key": "r",
        "circuit": circuit_to_dict(rat_with_resistor()),
        "series": [["R13", "1", "D1", "A"]],
    }
    got = client.post(
        "/api/stages/clipper", json={"circuit": rat, "ref": "D1", "arranged": [placed]}
    )
    assert [o["label"] for o in got.json()["options"] if o.get("key") == "r"] == [
        "1k in series: D1 + R13"
    ]


def test_a_level_at_any_amplitude_matches_the_named_picks(sim: Simulator) -> None:
    c = starter("ts808")
    view = stages_view(sim, c)
    assert view["picks"] == {"soft": 0.1, "med": 0.3, "hard": 1.0}
    at = stage_levels(sim, c, 0.3)
    assert [r["net"] for r in at["rows"]] == [r["net"] for r in view["rows"]]
    for row, got in zip(view["rows"], at["rows"], strict=True):
        cell = row["levels"]["med"]
        assert got["peak"] == pytest.approx(max(cell["up"], cell["down"]), rel=1e-6)
        assert got["predicted"] == pytest.approx(cell["predicted"], rel=1e-6)


def test_a_blocks_waveform_at_each_pick_is_the_panes_own_run(
    sim: Simulator, tmp_path: Path
) -> None:
    """D-127: a card's Waveform section draws the transients the pane measured; their
    peaks are the card's numbers."""
    c = starter("ts808")
    view = stages_view(sim, c)
    for row in view["rows"]:
        got = stage_waves(sim, c, row["net"])
        assert set(got["waves"]) == {"soft", "med", "hard"}
        assert len(got["time_ms"]) == len(got["waves"]["med"])
        assert got["time_ms"][0] == 0
        for lv, wave in got["waves"].items():
            cell = row["levels"][lv]  # peaks either side of its DC
            span = cell["up"] + cell["down"]
            assert max(wave) - min(wave) == pytest.approx(span, rel=0.05, abs=0.005)
    assert stage_waves(sim, c, "nowhere")["waves"] == {}
    settings = load_settings({"DATA_DIR": str(tmp_path / "data"),
                              "CACHE_DIR": str(tmp_path / "cache"),
                              "LIBRARY_DIR": str(REPO / "library")})  # fmt: skip
    client = TestClient(create_app(settings))
    net = view["rows"][0]["net"]
    body = {"circuit": circuit_to_dict(c), "net": net}
    answer = client.post("/api/stages/waves", json=body).json()
    assert set(answer["waves"]) == {"soft", "med", "hard"}
    assert client.post("/api/stages/waves", json={**body, "tone": 7}).status_code == 422


def test_the_ts808s_clipper_compresses_a_louder_guitar(sim: Simulator) -> None:
    c = starter("ts808")
    by = {r["label"]: r["net"] for r in stages_view(sim, c)["rows"]}
    quiet, loud = (stage_levels(sim, c, a) for a in (0.01, 1.0))
    peak = (
        {lv["net"]: lv["peak"] for lv in quiet["rows"]},
        {lv["net"]: lv["peak"] for lv in loud["rows"]},
    )
    gain_db = 20 * math.log10(peak[1][by["D1, D2"]] / peak[0][by["D1, D2"]])
    assert gain_db < 30  # 40 dB louder at the guitar, 10+ dB less at the diodes
    # unclipped, the prediction grows with the input
    pred = [{lv["net"]: lv["predicted"] for lv in r["rows"]}[by["D1, D2"]] for r in (quiet, loud)]
    assert 20 * math.log10(pred[1] / pred[0]) == pytest.approx(40, abs=3)


def test_a_transient_takes_a_pick_name_or_a_peak_in_range(sim: Simulator) -> None:
    c = starter("fuzz-face")
    assert sim.tran(c, ["out"], 0.25).level == "0.25 V"
    for wrong, said in (("loud", "Level must be"), (0.0, "above 0 V"), (20.0, "at most 10 V")):
        with pytest.raises(ValueError, match=said):
            sim.tran(c, ["out"], wrong)


def test_the_rats_clamp_follows_its_diodes(sim: Simulator) -> None:
    """The Rat's pair to ground with each kind of diode: a Schottky clamps low (about 0.3 V),
    silicon near 0.65 V, a red LED near 1.7 V. The point-contact germanium starts as low,
    but at the Rat's few mA its published curve has risen to about 0.5 V (D-253): between
    the two."""
    clamps = {}
    for kind, model in (("diode", "1N34A"), ("diode", "BAT46"), ("diode", "1N4148"),
                        ("led", "APT1608SURCK")):  # fmt: skip
        data = circuit_to_dict(starter("proco-rat"))
        for part in data["parts"]:
            if part["ref"] in ("D1", "D2"):
                part.update(type=kind, model=model)
        by = {r["label"]: r for r in stages_view(sim, parse_circuit(data))["rows"]}
        clamps[model] = by["D1, D2"]["clamp"]["up"]
    assert clamps["BAT46"] < 0.4 < clamps["1N34A"] < 0.55 < clamps["1N4148"] < 0.8
    assert 1.4 < clamps["APT1608SURCK"] < 2.0


def test_a_resistor_centres_the_big_muffs_input_booster(sim: Simulator) -> None:
    """D-119: Q4 sits high; each option is an E24 value that centres it, pushing no other
    stage off centre, and trying the first one the pane reads it centred."""
    muff = starter("big-muff-pi-v3")
    found = bias_options(sim, muff, "Q4")
    assert found["now"]["place"] == "sits high" and found["note"] is None
    options = found["options"]
    assert options and all(o["place"] == "centred" and o["others"] == [] for o in options)
    best = options[0]
    (ref,) = best["set"]
    to, was = best["set"][ref]["value"], best["undo"][ref]["value"]
    assert snap_to_series(parse_value(to), "E24") == pytest.approx(parse_value(to))
    assert best["label"] == f"{ref} {was} \u2192 {to}"
    assert best["text"].startswith(f"{best['label']}: Q4 centred")
    assert "gain " in best["text"] and "at a hard pick" in best["text"]
    tried = muff.with_part(ref, value=to)

    # its gain change (D-120): its own gain, base to collector (D-123)
    base = connect(muff).net_of("Q4", "B")

    def gain(c: Any) -> float:
        ac = sim.ac(c)
        at = [abs(float(np.interp(np.log10(200.0), np.log10(ac.freq), np.abs(ac.responses[n]))))
              for n in ("q4c", base)]  # fmt: skip
        return 20 * math.log10(at[0] / at[1])

    assert best["gain_db"] == pytest.approx(gain(tried) - gain(muff), abs=0.01)
    row = next(r for r in stages_view(sim, tried)["rows"] if r["label"] == "Q4")
    assert row["bias"]["place"] == "centred"
    assert row["bias"]["position"] == pytest.approx(best["position"])


def test_centring_says_when_it_cant_or_neednt(sim: Simulator) -> None:
    ff = bias_options(sim, starter("fuzz-face"), "Q1")  # sits by its emitter, by design
    assert ff["options"] == [] and ff["note"].startswith("No single resistor next to Q1")
    q2 = bias_options(sim, starter("fuzz-face"), "Q2")
    assert q2["options"] == [] and q2["note"] == "Q2 is centred already."
    with pytest.raises(FixError, match="R1 isn't a stage"):
        bias_options(sim, starter("fuzz-face"), "R1")


def test_bias_to_puts_a_stage_where_its_asked(sim: Simulator) -> None:
    """D-123: Bias to… is Centre's search aimed elsewhere: Q4 asked to sit at 30 % of its
    room gets resistor values that put it there, each saying which side clips first."""
    muff = starter("big-muff-pi-v3")
    found = bias_options(sim, muff, "Q4", 0.3)
    assert found["target"] == 0.3 and found["options"]
    for o in found["options"]:
        assert o["position"] == pytest.approx(0.3, abs=0.1)
        assert "sits low" in o["text"] and "clips the bottom first" in o["text"]
    (ref,) = found["options"][0]["set"]
    tried = muff.with_part(ref, **found["options"][0]["set"][ref])
    row = next(r for r in stages_view(sim, tried)["rows"] if r["label"] == "Q4")
    assert row["bias"]["position"] == pytest.approx(0.3, abs=0.1)


def test_how_far_bias_to_can_move_a_stage(sim: Simulator) -> None:
    """D-123: the bias bar greys what no part next to a stage reaches. The Big Muff's Q4
    reaches from about 13 % of its room to the top; the TS808's op-amps, biased from the
    shared reference, don't move; the reach always holds where it sits now."""
    q4 = bias_reach(sim, starter("big-muff-pi-v3"), "Q4")
    assert q4["lo"] == pytest.approx(0.13, abs=0.03) and q4["hi"] == pytest.approx(0.98)
    assert q4["lo"] <= q4["now"] <= q4["hi"]
    u1 = bias_reach(sim, starter("ts808"), "IC1A")
    assert u1["hi"] - u1["lo"] < 0.02 and not u1["aimable"]
    assert u1["why"].startswith("An op-amp's output sits where its + input is held, here 4.")
    assert q4["aimable"] and q4["why"] is None
    jfet = load_circuit(REPO / "tests" / "fixtures" / "circuits" / "jfet-drive.json")
    q1 = bias_reach(sim, jfet, "Q1")  # its trimmer, turned end to end without its target
    assert q1["lo"] < 0.3 and q1["hi"] > 0.9


def test_a_trimmer_with_a_target_gets_a_new_target(sim: Simulator) -> None:
    """D-123: a JFET's drain trimmer already turns itself to its target, so Bias to…
    moves the target, and that's the only option; the pane then reads it there."""
    jfet = load_circuit(REPO / "tests" / "fixtures" / "circuits" / "jfet-drive.json")
    found = bias_options(sim, jfet, "Q1", 0.7)
    (option,) = found["options"]
    assert set(option["set"]) == {"TR1"} and option["set"]["TR1"]["bias_target"]["node"] == "Q1.D"
    assert option["undo"]["TR1"] == {"rotation": 0.5, "bias_target": {"node": "Q1.D", "volts": 9.0}}
    assert option["label"].startswith("TR1 aimed at ")
    volts = option["set"]["TR1"]["bias_target"]["volts"]
    assert volts == round(volts, 2)  # to the bar's 10 mV, not the solver's 3.998
    assert 0 < option["set"]["TR1"]["rotation"] < 1  # the part shows where the solver turns it
    tried = jfet.with_part("TR1", bias_target={"node": "Q1.D", "volts": volts})
    row = next(r for r in stages_view(sim, tried)["rows"] if r["label"] == "Q1")
    assert row["bias"]["position"] == pytest.approx(0.7, abs=0.02)


def test_a_trimmer_with_no_target_is_turned_or_held(sim: Simulator) -> None:
    """D-123: with no target, the trimmer is turned there, or turned and given a target
    at the stage's output so it holds; both come before any resistor."""
    data = circuit_to_dict(
        load_circuit(REPO / "tests" / "fixtures" / "circuits" / "jfet-drive.json")
    )
    for part in data["parts"]:
        if part["ref"] == "TR1":
            del part["bias_target"]
    jfet = parse_circuit(data)
    found = bias_options(sim, jfet, "Q1", 0.6)
    turn, hold = found["options"][:2]
    assert set(turn["set"]["TR1"]) == {"rotation"} and turn["label"].startswith("Turn TR1 to ")
    assert hold["set"]["TR1"]["bias_target"]["node"] == "Q1.D"
    assert hold["undo"]["TR1"] == {"rotation": 0.5, "bias_target": None}
    turned = jfet.with_part("TR1", rotation=turn["set"]["TR1"]["rotation"])
    row = next(r for r in stages_view(sim, turned)["rows"] if r["label"] == "Q1")
    assert row["bias"]["position"] == pytest.approx(0.6, abs=0.02)


def test_the_gain_parts_get_sliders_with_what_clips_first(sim: Simulator) -> None:
    """D-125: the parts next to IC1B that move its own gain, biggest first by what +10 %
    does. R6 and the Drive pot get a slider over their values, sorted by gain, the value
    they have reading 0 dB; C3 (it moves a corner) gets none. Up the slider more clips,
    and sooner; each step's gain is what trying it gives."""
    ts = starter("ts808")
    seen: list[tuple[int, int]] = []
    found = gain_options(sim, ts, "IC1B", progress=lambda done, of: seen.append((done, of)))
    # the bar moves through each slider's values, not only part by part (Phase 8d)
    fractions = [d / of for d, of in seen]
    assert fractions == sorted(fractions)
    assert seen[-1][0] == seen[-1][1] > 30 and len(seen) > 30
    nudges = [abs(p["nudge_db"]) for p in found["parts"]]
    assert nudges == sorted(nudges, reverse=True)
    by = {p["ref"]: p for p in found["parts"]}
    assert by["C3"]["steps"] == [] and "where the curve bends" in by["C3"]["text"]
    r6 = by["R6"]["steps"]
    assert [s["gain_db"] for s in r6] == sorted(s["gain_db"] for s in r6)
    now = next(s for s in r6 if s["now"])
    assert now["value"] == "51k" and now["gain_db"] == pytest.approx(0.0, abs=1e-9)
    # as the pane measures it: D1, D2 clip from a soft pick (driven 4 / 9 / 13 dB)
    assert now["clips"] == {"soft": True, "med": True, "hard": True}
    assert r6[0]["value"] == "5k6" and r6[-1]["value"] == "470k"  # E12 (D-127)
    assert not r6[0]["clips"]["soft"] and r6[0]["chain"].startswith(
        "Clips first: D1, D2, from a medium pick (was soft)"
    )
    # R6 at the top of its E12 slider (470k, about ten times): a transient measures the
    # diodes driven 25 dB at a hard pick (26 dB with the 2N5089 buffer, before D-187; 25 dB
    # with onsemi's 1N4148 card, before D-159)
    assert r6[-1]["chain"].startswith(
        "Clips first: D1, D2, from a soft pick; at a hard pick driven 25 dB (was 13 dB)"
    )
    # a step's gain is what the stage gets with that value in
    top = gain_options(sim, ts.with_part("R6", value="470k"), "IC1B")
    assert top["gain_db"] - found["gain_db"] == pytest.approx(r6[-1]["own_db"], abs=0.01)
    drive = by["VR1"]["steps"]
    assert "turned full up" in drive[-1]["text"] and len(drive) > 3


def test_a_part_between_raises_the_stage_but_passes_less(sim: Simulator) -> None:
    """D-223 (the user's TODO, 2026-11-09): the BD-2's R12 runs from Q4's collector into
    the clipping diodes. A bigger R12 loads the stage less, so its own gain rises, but less
    reaches the diodes: the slider is spread by what reaches them, so up is louder."""
    found = gain_options(sim, starter("boss-bd2-aion"), "Q4")
    assert found["into"] == "D2, D3, D4, D5"
    r12 = next(p for p in found["parts"] if p["ref"] == "R12")["steps"]
    big = next(s for s in r12 if s["value"] == "680k")
    assert big["own_db"] > 0 > big["gain_db"] + 3  # the stage up, the diodes 3 dB or more down
    assert "into D2, D3, D4, D5 \u2212" in big["text"]
    assert [s["gain_db"] for s in r12] == sorted(s["gain_db"] for s in r12)
    assert r12[-1]["value"] != "680k"  # the louder end of the slider is a smaller R12


def test_the_chain_estimate_matches_what_is_measured(sim: Simulator) -> None:
    """D-125: on the starters, the estimate a slider reads clips the same rows at the same
    picks as the transients the pane measures."""
    from solum.fixes import clipper_knees, estimate_chain

    for name in ("ts808", "proco-rat", "big-muff-pi-v3"):
        c = starter(name)
        measured = stages_view(sim, c)["rows"]
        guess = estimate_chain(sim, c, clipper_knees(sim, c))
        assert guess is not None
        for lv in ("soft", "med", "hard"):
            got = [r.clips for r in guess[lv]]
            want = [bool(r["levels"][lv]["clips"]) for r in measured]
            assert got == want, (name, lv)


def test_a_gain_slider_stops_before_a_stage_loses_its_bias(sim: Simulator) -> None:
    """D-125: the Big Muff's Q4 is cut off well inside ten times R9, so its slider stops
    before that and says why, rather than reading tens of dB down."""
    found = gain_options(sim, starter("big-muff-pi-v3"), "Q4")
    r9 = next(p for p in found["parts"] if p["ref"] == "R9")
    assert "Q4 runs into its limit at DC" in r9["note"]
    assert max(parse_value(s["value"]) for s in r9["steps"]) < 4.7e6
    assert min(s["gain_db"] for s in r9["steps"]) > -20


def test_clipper_swaps_are_measured(sim: Simulator) -> None:
    """D-123: every other diode type for the Rat's pair, and the second one an LED
    (lopsided: it clamps higher one way)."""
    found = clipper_options(sim, starter("proco-rat"), "D1")
    by = {o["label"]: o for o in found["options"]}
    pair = "D1, D2 \u2192 "
    assert set(by) == {
        f"{pair}1N34A (germanium)", f"{pair}BAT46 (Schottky)", f"{pair}APT1608SURCK (red LED)",
        "D2 \u2192 APT1608SURCK (red LED), lopsided",
    }  # fmt: skip
    led = by[f"{pair}APT1608SURCK (red LED)"]
    assert 1.4 < led["up"] < 2.0 and led["louder_db"] > 3
    lop = by["D2 \u2192 APT1608SURCK (red LED), lopsided"]
    assert lop["set"] == {"D2": {"type": "led", "model": "APT1608SURCK"}}
    assert lop["undo"] == {"D2": {"type": "diode", "model": "1N4148"}}
    assert max(lop["up"], lop["down"]) > 2 * min(lop["up"], lop["down"])
    with pytest.raises(FixError, match="isn't a clipper"):
        clipper_options(sim, starter("proco-rat"), "IC1")


def rat_with_resistor(*, short: bool = False) -> Any:
    """The Rat with a 1k between D1's anode and its ground symbol, as the browser places
    it (D-124): the symbol moved to the resistor's far end. `short` leaves a ground
    symbol on D1 too, so the resistor does nothing (a placement gone wrong)."""
    d = circuit_to_dict(starter("proco-rat"))
    d["parts"].append(
        {"ref": "R13", "type": "resistor", "value": "1k", "pos": [530, 60], "rot": 90}
    )
    d["labels"] = [lb for lb in d["labels"] if list(lb["pos"]) != [530, 40]]
    d["labels"] += [{"net": "GND", "pos": [530, 80]}]
    if short:
        d["labels"] += [{"net": "GND", "pos": [530, 40]}]
    return parse_circuit(d)


def test_clipper_arrangements_are_checked_and_measured(sim: Simulator) -> None:
    """D-124: an arrangement placed by the browser is measured like a swap, worded from
    what it adds; one that doesn't connect as it says (the resistor shorted) is left out
    with a note."""
    rat = starter("proco-rat")
    series = (("R13", "1", "D1", "A"),)
    found = clipper_options(
        sim,
        rat,
        "D1",
        arranged=[
            Arranged("resistor 1k", rat_with_resistor(), series),
            Arranged("shorted", rat_with_resistor(short=True), series),
        ],
    )
    (one,) = [o for o in found["options"] if "key" in o]
    assert one["key"] == "resistor 1k" and one["set"] == {} and one["undo"] == {}
    assert one["label"] == "1k in series: D1 + R13"
    # D1 (anode to ground) holds the swing down: that way clamps further off, D2's doesn't move
    now = found["now"]
    assert one["up"] == pytest.approx(now["up"], abs=0.05)
    assert one["down"] > now["down"] + 0.2
    assert found["note"].startswith("There isn't room to add parts beside D1 cleanly")


def test_room_made_for_an_arrangement_must_keep_every_connection(sim: Simulator) -> None:
    """D-124: room made first (parts moved, nothing added) is checked on its own: one that
    joins the same pins as before is fine; one that parted D1 from ground isn't offered,
    and the note says so."""
    rat = starter("proco-rat")
    series = (("R13", "1", "D1", "A"),)
    parted = circuit_to_dict(rat)  # D1's ground symbol moved off its pin: D1 floats
    parted["labels"] = [lb for lb in parted["labels"] if list(lb["pos"]) != [530, 40]]
    parted["labels"] += [{"net": "GND", "pos": [530, 80]}]
    found = clipper_options(
        sim,
        rat,
        "D1",
        arranged=[
            Arranged("kept", rat_with_resistor(), series, room=rat),
            Arranged("parted", rat_with_resistor(), series, room=parse_circuit(parted)),
        ],
    )
    assert [o["key"] for o in found["options"] if "key" in o] == ["kept"]
    assert found["note"].startswith("Making room beside D1 would have changed what's connected")


def test_arrows_carry_the_passive_losses_between_stages(sim: Simulator) -> None:
    """D-123: an arrow's loss is from the row before's net to where the signal enters
    the next (its base); with the next block's own gain, base to collector, the two add
    up to the gain from one row's net to the next's. The Big Muff's tone stack loses
    over 5 dB into Q1; a clipper in feedback has no arrow of its own."""
    muff = starter("big-muff-pi-v3")
    view = stages_view(sim, muff)
    labels = [r["label"] for r in view["rows"]]
    assert len(view["arrows"]) == len(labels) + 1
    q1 = labels.index("Q1")
    tone_stack = view["arrows"][q1]
    assert tone_stack is not None and tone_stack["200"] < -5
    assert view["arrows"][labels.index("D3, D4")] is None  # in Q3's feedback
    ac = sim.ac(muff)

    def at(net: str) -> float:
        return float(np.interp(np.log10(200.0), np.log10(ac.freq), np.abs(ac.responses[net])))

    before, row = view["rows"][q1 - 1], view["rows"][q1]
    whole = 20 * math.log10(at(row["net"]) / at(before["net"]))
    assert tone_stack["200"] + row["gain_db"]["200"] == pytest.approx(whole, abs=0.01)
    # the last arrow ends at the amp: the Volume pot's loss
    assert view["arrows"][-1] is not None
