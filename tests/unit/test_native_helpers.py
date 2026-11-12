import pytest

from solum.sim import native
from solum.sim.engine import EngineStuck, EngineUnavailable


@pytest.mark.parametrize(
    ("line", "is_error"),
    [
        ("stderr Error: unknown subckt: x1", True),
        ("stderr Error on line:", True),
        ("stderr MIF-ERROR - unable to find definition of model a$poly", True),
        ("stderr Fatal error in ...", True),
        ("stderr Warning: Model issue on line 5 :", False),
        ("stderr unrecognized parameter (isr) - ignored", False),
        ("stdout Circuit: test", False),
    ],
)
def test_is_error_line(line: str, is_error: bool) -> None:
    assert native.is_error_line(line) is is_error


def test_find_library_prefers_explicit_path() -> None:
    assert native.find_library("/opt/libngspice.so") == "/opt/libngspice.so"


def test_find_library_missing_says_what_to_do(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(native.ctypes.util, "find_library", lambda _name: None)
    with pytest.raises(EngineUnavailable, match="Use the Docker image"):
        native.find_library(None)


def test_unloadable_library_is_unavailable() -> None:
    with pytest.raises(EngineUnavailable, match="Couldn't load ngspice"):
        native.NativeNgspice("/nonexistent/libngspice.so")


class _SpinningLib:
    """ngspice's library as it is after a halt it ignored: still running."""

    def __init__(self) -> None:
        self.running = True
        self.commands: list[bytes] = []

    def ngSpice_Command(self, command: bytes) -> int:
        self.commands.append(command)
        return 0

    def ngSpice_running(self) -> bool:
        return self.running


def test_a_run_that_ignores_its_halt_leaves_the_engine_stuck_and_saying_so(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """D-279: a solve that never stops is told at once, and so is every later run, with
    what to do; they don't each wait out a timeout. If it stops after all, runs go on."""
    import threading

    monkeypatch.setattr(native, "HALT_WAIT", 0.01)
    engine = object.__new__(native.NativeNgspice)
    engine._lib = lib = _SpinningLib()
    engine._lock = threading.Lock()
    engine._finished = threading.Event()
    engine._stopped = None
    engine._progress = None
    engine._stuck = False
    engine._exited = False
    engine._output = []
    with pytest.raises(EngineStuck, match=r"got stuck on this circuit .* Restart Solum Builder"):
        engine._run_in_background(0.01)
    assert lib.commands == [b"bg_run", b"bg_halt"]
    with pytest.raises(EngineStuck, match=r"stuck on an earlier circuit .* Restart"):
        engine.run("t\n.op\n.end")
    assert lib.commands == [b"bg_run", b"bg_halt"]  # nothing was sent to it
    lib.running = False  # it stopped in the end: the next run is tried
    monkeypatch.setattr(engine, "_run_locked", lambda netlist, timeout: "ran")
    assert engine.run("t\n.op\n.end") == "ran" and engine._stuck is False
