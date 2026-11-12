import pytest

from solum.sim.native import NativeNgspice, native_engine


@pytest.fixture(scope="session")
def engine() -> NativeNgspice:
    return native_engine()
