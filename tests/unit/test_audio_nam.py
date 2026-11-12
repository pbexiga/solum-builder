"""The numpy NAM forward pass against the official package's output (D-026).

`tests/fixtures/nam/standard-random.*`: a "standard"-size WaveNet with random weights,
exported by neural-amp-modeler 0.13 (PyTorch 2.14, CPU) in the Phase 0 spike, with the
package's own output for an 8 s test signal (first 12 000 samples kept; the model is
causal, so they depend only on the first 12 000 inputs).
"""

import json
from pathlib import Path
from typing import Any

import numpy as np
import pytest

from solum.audio.nam import NamError, activation, load_nam, run_nam

FIXTURES = Path(__file__).resolve().parents[1] / "fixtures" / "nam"


def standard() -> dict[str, Any]:
    doc: dict[str, Any] = json.loads((FIXTURES / "standard-random.nam").read_text())
    return doc


def as_v05(doc: dict[str, Any]) -> dict[str, Any]:
    """The same capture in the v0.5 config spelling (the weights' order is the same)."""
    layers = [
        {
            "input_size": la["input_size"],
            "condition_size": la["condition_size"],
            "head_size": la["head"]["out_channels"],
            "channels": la["channels"],
            "kernel_size": la["kernel_sizes"][0],
            "dilations": la["dilations"],
            "activation": "Tanh",
            "gated": False,
            "head_bias": la["head"]["bias"],
        }
        for la in doc["config"]["layers"]
    ]
    return {**doc, "version": "0.5.2", "config": {"layers": layers, "head_scale": 0.02}}


@pytest.mark.parametrize("spelling", ["v0.7", "v0.5"])
def test_matches_the_official_package(spelling: str) -> None:
    doc = standard() if spelling == "v0.7" else as_v05(standard())
    model = load_nam(json.dumps(doc).encode())
    x = np.load(FIXTURES / "standard-random.in.npy")
    expected = np.load(FIXTURES / "standard-random.out.npy")
    y = run_nam(model, x)
    assert len(y) == len(x)
    assert np.max(np.abs(y - expected)) < 1e-6 * max(1.0, float(np.max(np.abs(expected))))
    assert model.receptive_field == 1 + 2 * 2 * sum(2**i for i in range(10))  # two arrays, k=3
    assert model.sample_rate == 48000
    assert model.input_level_dbu is None


def slimmable() -> dict[str, Any]:
    doc: dict[str, Any] = json.loads((FIXTURES / "slimmable-random.nam").read_text())
    return doc


def test_slimmable_container_plays_its_full_size_model() -> None:
    """`slimmable-random.nam`: the layout of a 2026 Tone3000 capture (SlimmableContainer of
    a 3- and an 8-channel WaveNet; LeakyReLU, kernels 6 and 15, a 16-tap head), random
    weights, and the official package's output of the 8-channel one (`.out.npy`)."""
    model = load_nam((FIXTURES / "slimmable-random.nam").read_bytes())
    x = np.load(FIXTURES / "standard-random.in.npy")
    expected = np.load(FIXTURES / "slimmable-random.out.npy")
    y = run_nam(model, x)
    assert len(y) == len(x)
    assert np.max(np.abs(y - expected)) < 1e-5 * max(1.0, float(np.max(np.abs(expected))))
    la = slimmable()["config"]["submodels"][0]["model"]["config"]["layers"][0]
    body = sum(d * (k - 1) for k, d in zip(la["kernel_sizes"], la["dilations"], strict=True))
    assert model.receptive_field == 1 + body + 15
    assert (model.input_level_dbu, model.name, model.sample_rate) == (12, "slimmable random", 48000)


def test_slimmable_container_picks_the_largest_max_value() -> None:
    doc = slimmable()
    doc["config"]["submodels"].reverse()
    model = load_nam(json.dumps(doc).encode())
    assert model.arrays[0].rechannel.shape == (8, 1)


@pytest.mark.parametrize(
    ("spec", "x", "y"),
    [
        ({"type": "LeakyReLU", "negative_slope": 0.01}, [-2.0, 0.0, 3.0], [-0.02, 0.0, 3.0]),
        ({"type": "LeakyReLU"}, [-2.0, 3.0], [-0.02, 3.0]),  # torch's default slope
        (
            {"type": "LeakyHardtanh", "min_slope": 0.1, "max_slope": 0.2},
            [-3.0, 0.5, 2.0],
            [-1.2, 0.5, 1.2],
        ),
        ({"type": "Softsign"}, [-1.0, 0.0, 3.0], [-0.5, 0.0, 0.75]),
        ("Tanh", [0.5], [0.46211716]),
    ],
)
def test_activations(spec: Any, x: list[float], y: list[float]) -> None:
    f = activation(spec)
    assert f(np.array(x, np.float32)) == pytest.approx(y, abs=1e-6)


def test_metadata_sample_rate_and_level() -> None:
    doc = standard() | {"sample_rate": 44100}
    doc["metadata"] = {"input_level_dbu": 12.5, "name": "Test amp"}
    model = load_nam(json.dumps(doc).encode())
    assert (model.sample_rate, model.input_level_dbu, model.name) == (44100, 12.5, "Test amp")


def test_silence_in_silence_out_shape() -> None:
    model = load_nam((FIXTURES / "standard-random.nam").read_bytes())
    assert run_nam(model, np.zeros(0)).shape == (0,)


@pytest.mark.parametrize(
    ("change", "message"),
    [
        (lambda d: d.update(architecture="LSTM"), "LSTM architecture"),
        (lambda d: d["config"]["layers"][0].update(gating_mode=["gated"] * 10), "gated"),
        (lambda d: d["config"]["layers"][0]["activation_pre_film"].update(active=True), "FiLM"),
        (lambda d: d["config"]["layers"][0].update(activation=[{"type": "Swish"}] * 10), "Swish"),
        (lambda d: d["weights"].pop(), "damaged"),
        (lambda d: d["weights"].append(0.0), "damaged"),
        (lambda d: d["config"]["layers"][0].pop("channels"), "damaged"),
    ],
)
def test_unsupported_or_damaged_captures_are_refused(change: Any, message: str) -> None:
    doc = standard()
    change(doc)
    with pytest.raises(NamError, match=message):
        load_nam(json.dumps(doc).encode())


@pytest.mark.parametrize(
    ("change", "message"),
    [
        (lambda d: d["config"].update(submodels=[]), "damaged"),
        (lambda d: d["config"]["submodels"][0]["model"].update(architecture="LSTM"), "LSTM"),
        (
            lambda d: d["config"]["submodels"][0]["model"]["config"].update(head={"channels": 4}),
            "output head",
        ),
        (
            lambda d: d["config"]["submodels"][0]["model"]["config"]["layers"][0].update(
                slimmable={"method": "slice_channels_uniform", "kwargs": {}}
            ),
            "slimmable layers",
        ),
    ],
)
def test_unsupported_or_damaged_containers_are_refused(change: Any, message: str) -> None:
    doc = slimmable()
    change(doc)
    with pytest.raises(NamError, match=message):
        load_nam(json.dumps(doc).encode())


def test_not_json() -> None:
    with pytest.raises(NamError, match="isn't a NAM capture"):
        load_nam(b"RIFF....WAVE")
