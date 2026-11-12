"""Every model's validation record still holds: re-measure, compare, check the datasheet."""

from pathlib import Path

import pytest

from solum.model_checks import measure
from solum.models import ModelLibrary, load_models
from solum.sim.native import NativeNgspice

REPO = Path(__file__).parents[2]
LIBRARY = load_models([REPO / "library" / "models"])
CASES = [
    pytest.param(model_id, i, id=f"{model_id}-{v.quantity}-{i}")
    for model_id in LIBRARY.ids()
    for i, v in enumerate(LIBRARY.get(model_id).info.validation)
]


@pytest.fixture(scope="module")
def models() -> ModelLibrary:
    return LIBRARY


@pytest.mark.parametrize(("model_id", "index"), CASES)
def test_validation_record(
    engine: NativeNgspice, models: ModelLibrary, model_id: str, index: int
) -> None:
    model = models.get(model_id)
    record = model.info.validation[index]
    value = measure(engine, models, model, record.quantity, record.conditions)
    assert value == pytest.approx(record.simulated, rel=2e-3), "model or pipeline changed"
    ds = record.datasheet
    if ds is not None:
        if ds.min is not None:
            assert value >= ds.min, f"below datasheet min ({ds.source})"
        if ds.max is not None:
            assert value <= ds.max, f"above datasheet max ({ds.source})"
        if ds.typ is not None and ds.tol is not None:
            assert value == pytest.approx(ds.typ, abs=ds.tol), (
                f"off datasheet typical ({ds.source})"
            )


def _gummel_poon(model_id: str) -> object:
    """The library card as `scripts/fit_models.py`'s GummelPoon (it agrees with ngspice)."""
    import importlib.util
    import re

    spec = importlib.util.spec_from_file_location("fit_models", REPO / "scripts" / "fit_models.py")
    assert spec and spec.loader
    fit = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(fit)
    card = (REPO / "library" / "models" / "bjt" / f"{model_id}.lib").read_text()
    params = {k: float(v) for k, v in re.findall(r"(\w+)=([-+\d.e]+)", card.split(".model", 1)[1])}
    params["is_"] = params.pop("is")
    return fit.GummelPoon(**{"vaf": float("inf"), "ise": 0.0, "ne": 1.5, **params})


def test_hfe_is_read_at_the_current_asked_for(engine: NativeNgspice, models: ModelLibrary) -> None:
    """Where the gain falls steeply (the 2N3904 at 100 mA), a fixed number of guesses at
    the base current lands off the current asked for (the MPSA06 read 282 mA for 300)."""
    q = _gummel_poon("2N3904")
    for ic in (1e-3, 0.1, 0.2):
        got = measure(engine, models, models.get("2N3904"), "hfe", {"ic": ic, "vce": 1.0})
        assert got == pytest.approx(q.forward(ic, 1.0)[1], rel=1e-3)  # type: ignore[attr-defined]
