"""NAM amp captures (`.nam` files): the classic WaveNet forward pass in numpy (D-026).

Supported: architecture "WaveNet" with ungated layers, groups of 1, no FiLM, no head 1x1
and no output head, in either config spelling: v0.5 (`kernel_size`, `head_size`,
`activation: "Tanh"`) or v0.7 (`kernel_sizes`, `head: {...}` whose kernel may be wider
than 1, an activation per layer, with parameters). A "SlimmableContainer" (several WaveNets
of different sizes, as Tone3000 exports since 2026) plays its largest one, as the plugin
does by default. Anything else is refused with a plain message.

Weights are one flat list, in this order per layer array: rechannel (no bias); per layer:
dilated conv (weight, bias), input mixer (no bias), 1x1 (weight, bias); head conv (weight,
bias if any). The head scale is last. Checked against the official package's output
(`tests/unit/test_audio_nam.py`).
"""

import json
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

import numpy as np
import numpy.typing as npt

F32 = npt.NDArray[np.float32]

DEFAULT_RATE = 48000  # captures without a `sample_rate` are 48 kHz


class NamError(ValueError):
    """The capture can't be used (plain-English message)."""


Activation = Callable[[F32], F32]


def _sigmoid(z: F32) -> F32:
    return np.asarray(1 / (1 + np.exp(-z)), dtype=np.float32)


def _leaky_relu(negative_slope: float = 0.01) -> Activation:
    return lambda z: np.where(z < 0, z * np.float32(negative_slope), z)


def _hardtanh(min_val: float = -1.0, max_val: float = 1.0) -> Activation:
    return lambda z: np.clip(z, min_val, max_val, out=z)


def _leaky_hardtanh(
    min_val: float = -1.0, max_val: float = 1.0, min_slope: float = 0.01, max_slope: float = 0.01
) -> Activation:
    def f(z: F32) -> F32:
        low = (z - np.float32(min_val)) * np.float32(min_slope) + np.float32(min_val)
        high = (z - np.float32(max_val)) * np.float32(max_slope) + np.float32(max_val)
        return np.where(z < min_val, low, np.where(z > max_val, high, z))

    return f


# Name (lower case) → maker taking the file's parameters, as the official package spells them.
ACTIVATIONS: dict[str, Callable[..., Activation]] = {
    "tanh": lambda: np.tanh,
    "relu": lambda: lambda z: np.maximum(z, 0, out=z),
    "sigmoid": lambda: _sigmoid,
    "softsign": lambda: lambda z: z / (1 + np.abs(z)),
    "hardtanh": _hardtanh,
    "leakyrelu": _leaky_relu,
    "leakyhardtanh": _leaky_hardtanh,
}


@dataclass(frozen=True)
class Layer:
    dilation: int
    activation: Activation
    conv_w: F32  # (ch, ch, k)
    conv_b: F32
    mix_w: F32  # (ch, cond)
    out_w: F32  # 1x1: (ch, ch)
    out_b: F32


@dataclass(frozen=True)
class LayerArray:
    rechannel: F32  # (ch, in)
    layers: tuple[Layer, ...]
    head_w: F32  # (out, ch, k)
    head_b: F32 | None


@dataclass(frozen=True)
class NamModel:
    arrays: tuple[LayerArray, ...]
    head_scale: float
    receptive_field: int
    sample_rate: int
    input_level_dbu: float | None  # metadata: the analog level of a 0 dBFS input, if given
    name: str


class _Weights:
    def __init__(self, flat: list[float]) -> None:
        self.w = np.asarray(flat, dtype=np.float32)
        self.i = 0

    def take(self, *shape: int) -> F32:
        n = int(np.prod(shape))
        if self.i + n > len(self.w):
            raise NamError("This capture's weights don't match its settings; the file is damaged.")
        out = self.w[self.i : self.i + n].reshape(shape)
        self.i += n
        return out


def _unsupported(what: str) -> NamError:
    return NamError(
        f"This capture uses {what}, which Solum Builder can't play yet. Most captures are standard "
        "WaveNet ones; try another capture of this amp."
    )


def activation(spec: Any) -> Activation:
    """A layer's activation from the file: a name ("Tanh") or `{"type": ..., **params}`."""
    params = dict(spec) if isinstance(spec, dict) else {}
    name = params.pop("type", spec)
    if not isinstance(name, str) or name.lower() not in ACTIVATIONS:
        raise _unsupported(f"the {name} activation")
    try:
        return ACTIVATIONS[name.lower()](**params)
    except TypeError:
        raise _unsupported(f"the {name} activation with settings {sorted(params)}") from None


def _layer_specs(
    la: dict[str, Any],
) -> tuple[list[int], list[int], list[Activation], int, int, bool]:
    """Kernel sizes, dilations, activations, head size, head kernel and head bias, in
    either spelling."""
    dilations = [int(d) for d in la["dilations"]]
    n = len(dilations)
    if "kernel_sizes" in la:  # v0.7
        kernels = [int(k) for k in la["kernel_sizes"]]
        acts = [activation(a) for a in la["activation"]]
        if any(g != "none" for g in la.get("gating_mode", ["none"] * n)):
            raise _unsupported("gated layers")
        if la.get("head1x1", {}).get("active") or not la.get("layer1x1", {}).get("active", True):
            raise _unsupported("a non-standard layer layout")
        if la.get("groups_input", 1) != 1 or la.get("bottleneck", la["channels"]) != la["channels"]:
            raise _unsupported("grouped or bottlenecked layers")
        films = [k for k, v in la.items() if k.endswith("film") and v.get("active")]
        if films:
            raise _unsupported("FiLM conditioning")
        if la.get("slimmable") is not None:
            raise _unsupported("slimmable layers")
        head = la["head"]
        size, kernel = int(head["out_channels"]), int(head.get("kernel_size", 1))
        return kernels, dilations, acts, size, kernel, bool(head["bias"])
    if la.get("gated"):  # v0.5
        raise _unsupported("gated layers")
    act = activation(la["activation"])
    return (
        [int(la["kernel_size"])] * n,
        dilations,
        [act] * n,
        int(la["head_size"]),
        1,
        bool(la["head_bias"]),
    )


def _largest_submodel(doc: dict[str, Any]) -> dict[str, Any]:
    """A SlimmableContainer's full-size model, with the container's metadata and rate."""
    try:
        best = max(doc["config"]["submodels"], key=lambda s: float(s["max_value"]))
        model = dict(best["model"])
    except (ValueError, KeyError, TypeError):
        raise NamError("This capture's settings are incomplete; the file is damaged.") from None
    model["metadata"] = (model.get("metadata") or {}) | (doc.get("metadata") or {})
    model["sample_rate"] = doc.get("sample_rate") or model.get("sample_rate")
    return model


def load_nam(data: bytes) -> NamModel:
    """A `.nam` file's model. NamError if it isn't one Solum Builder can run."""
    try:
        doc = json.loads(data)
        if doc["architecture"] == "SlimmableContainer":
            doc = _largest_submodel(doc)
        arch, config, flat = doc["architecture"], doc["config"], doc["weights"]
    except (ValueError, KeyError, TypeError) as err:
        if isinstance(err, NamError):
            raise
        raise NamError("This isn't a NAM capture (.nam file).") from None
    if arch != "WaveNet":
        raise _unsupported(f"the {arch} architecture")
    if config.get("head") is not None or config.get("condition_dsp") is not None:
        raise _unsupported("an output head")
    weights = _Weights(flat)
    arrays = []
    try:
        for la in config["layers"]:
            kernels, dilations, acts, head_size, head_k, head_bias = _layer_specs(la)
            ch, cin, cond = int(la["channels"]), int(la["input_size"]), int(la["condition_size"])
            rechannel = weights.take(ch, cin)
            layers = tuple(
                Layer(
                    d,
                    a,
                    weights.take(ch, ch, k),
                    weights.take(ch),
                    weights.take(ch, cond),
                    weights.take(ch, ch),
                    weights.take(ch),
                )
                for k, d, a in zip(kernels, dilations, acts, strict=True)
            )
            head_w = weights.take(head_size, ch, head_k)
            head_b = weights.take(head_size) if head_bias else None
            arrays.append(LayerArray(rechannel, layers, head_w, head_b))
        head_scale = float(weights.take(1)[0])
    except (KeyError, TypeError, ValueError) as err:
        if isinstance(err, NamError):
            raise
        raise NamError("This capture's settings are incomplete; the file is damaged.") from None
    if weights.i != len(weights.w):
        raise NamError("This capture's weights don't match its settings; the file is damaged.")
    rf = 1 + sum(
        a.head_w.shape[2] - 1 + sum(la.dilation * (la.conv_w.shape[2] - 1) for la in a.layers)
        for a in arrays
    )
    meta = doc.get("metadata") or {}
    level = meta.get("input_level_dbu")
    return NamModel(
        arrays=tuple(arrays),
        head_scale=head_scale,
        receptive_field=rf,
        sample_rate=int(doc.get("sample_rate") or DEFAULT_RATE),
        input_level_dbu=float(level) if isinstance(level, int | float) else None,
        name=str(meta.get("name") or ""),
    )


def _conv(x: F32, w: F32, b: F32 | None, d: int) -> F32:
    """Causal dilated convolution without padding: output is `d * (k - 1)` shorter."""
    k = w.shape[2]
    n = x.shape[1] - d * (k - 1)
    y = w[:, :, 0] @ x[:, :n]
    for j in range(1, k):
        y += w[:, :, j] @ x[:, j * d : j * d + n]
    if b is not None:
        y += b[:, None]
    return y


def _tail(x: F32, n: int) -> F32:
    """The last `n` columns (`x[:, -n:]` is all of them when n is 0)."""
    return x[:, x.shape[1] - n :]


def run_nam(model: NamModel, x: npt.NDArray[np.floating[Any]]) -> F32:
    """The capture's output for input `x` (at `model.sample_rate`, full scale ±1), same
    length; the input starts from silence."""
    pad = np.zeros(model.receptive_field - 1, np.float32)
    cond = np.concatenate([pad, np.asarray(x, np.float32)])[None, :]
    y, head = cond, None
    for a in model.arrays:
        h = a.rechannel @ y
        for layer in a.layers:
            z = _conv(h, layer.conv_w, layer.conv_b, layer.dilation)
            n = z.shape[1]
            z += layer.mix_w @ _tail(cond, n)
            z = layer.activation(z)
            head = z if head is None else _tail(head, n) + z
            h = _tail(h, n) + layer.out_w @ z + layer.out_b[:, None]
        assert head is not None
        head = _conv(head, a.head_w, a.head_b, 1)
        y = _tail(h, head.shape[1])
    assert head is not None
    return np.asarray(model.head_scale * head[0], dtype=np.float32)
