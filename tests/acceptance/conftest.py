from pathlib import Path

import pytest

from solum.models import ModelLibrary, load_models
from solum.sim.native import native_engine
from solum.simulate import Simulator

REPO = Path(__file__).parents[2]


@pytest.fixture(scope="session")
def models() -> ModelLibrary:
    return load_models([REPO / "library" / "models"])


@pytest.fixture(scope="session")
def sim(models: ModelLibrary) -> Simulator:
    return Simulator(native_engine(), models)
