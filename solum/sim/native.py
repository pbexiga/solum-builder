"""Native ngspice through its shared library (`libngspice`) via ctypes.

ngspice keeps global state, so there is one instance per process and every call
is serialised by a lock. Parallel runs (render sweeps) need separate processes.

Some netlist errors leave ngspice "awaiting reset" (it calls ControlledExit). The
engine then unloads and reloads the library so the next run starts clean.
"""

import _ctypes
import ctypes
import ctypes.util
import re
import threading
import time
from collections.abc import Callable
from ctypes import POINTER, c_bool, c_char_p, c_double, c_int, c_short, c_void_p

import numpy as np

from solum.sim.engine import (
    DEFAULT_TIMEOUT,
    EngineStuck,
    EngineUnavailable,
    Plot,
    SimError,
    SimResult,
    SimTimeout,
    Vector,
    prepare_netlist,
)

_VF_COMPLEX = 2  # ngspice vector flag: data is in v_compdata
HALT_WAIT = 5.0  # seconds a halted run gets to stop
RESTART = "Restart Solum Builder (docker compose restart, or stop and start it) to simulate again."
STUCK_ON_THIS = (
    "The simulator got stuck on this circuit and couldn't be stopped: its DC solve never "
    "settles, usually a chip or model wired the wrong way round. Undo the last change, then: "
    + RESTART
)
STUCK_SINCE = "The simulator got stuck on an earlier circuit and can't run. " + RESTART
_PERCENT = re.compile(r"(\d+(?:\.\d+)?)%")


class _NgComplex(ctypes.Structure):
    _fields_ = (("cx_real", c_double), ("cx_imag", c_double))


class _VectorInfo(ctypes.Structure):
    _fields_ = (
        ("v_name", c_char_p),
        ("v_type", c_int),
        ("v_flags", c_short),
        ("v_realdata", POINTER(c_double)),
        ("v_compdata", POINTER(_NgComplex)),
        ("v_length", c_int),
    )


_SendChar = ctypes.CFUNCTYPE(c_int, c_char_p, c_int, c_void_p)
_SendStat = ctypes.CFUNCTYPE(c_int, c_char_p, c_int, c_void_p)
_ControlledExit = ctypes.CFUNCTYPE(c_int, c_int, c_bool, c_bool, c_int, c_void_p)
_BGThreadRunning = ctypes.CFUNCTYPE(c_int, c_bool, c_int, c_void_p)

_instances: dict[str, "NativeNgspice"] = {}
_instances_lock = threading.Lock()


def find_library(explicit: str | None = None) -> str:
    """Path or soname of libngspice. Raises EngineUnavailable if not installed."""
    if explicit:
        return explicit
    found = ctypes.util.find_library("ngspice")
    if found is None:
        raise EngineUnavailable(
            "ngspice isn't installed (libngspice not found). Use the Docker image, or install "
            "your system's libngspice package, or set NGSPICE_LIBRARY to its path."
        )
    return found


def native_engine(library: str | None = None) -> "NativeNgspice":
    """The process-wide native engine (created on first use)."""
    path = find_library(library)
    with _instances_lock:
        if path not in _instances:
            _instances[path] = NativeNgspice(path)
        return _instances[path]


def is_error_line(line: str) -> bool:
    """True if an ngspice output line reports an error (not a warning or note)."""
    words = line.removeprefix("stderr ").lower().split()
    if not words:
        return False
    return "error" in words[0] or words[0] == "fatal" or "error:" in words


class NativeNgspice:
    name = "native"

    def __init__(self, library_path: str) -> None:
        self._path = library_path
        self._lock = threading.Lock()
        self._output: list[str] = []
        self._finished = threading.Event()  # set when ngspice's background run ends
        self._progress: Callable[[float], None] | None = None
        self._stopped: Exception | None = None  # what the progress callback raised
        self._stuck = False  # a halted run never stopped: nothing runs again (`EngineStuck`)
        # Keep callback objects alive for the life of the engine.
        self._callbacks = (
            _SendChar(self._on_char),
            _SendStat(self._on_stat),
            _ControlledExit(self._on_exit),
            _BGThreadRunning(self._on_background),
        )
        self._load()
        self._version = self._read_version()

    def _load(self) -> None:
        try:
            lib = ctypes.CDLL(self._path)
        except OSError as err:
            raise EngineUnavailable(f"Couldn't load ngspice from {self._path}: {err}") from err
        lib.ngSpice_Init.argtypes = (
            _SendChar, _SendStat, _ControlledExit, c_void_p, c_void_p, _BGThreadRunning, c_void_p,
        )  # fmt: skip
        lib.ngSpice_Command.argtypes = (c_char_p,)
        lib.ngSpice_Circ.argtypes = (POINTER(c_char_p),)
        lib.ngGet_Vec_Info.argtypes = (c_char_p,)
        lib.ngGet_Vec_Info.restype = POINTER(_VectorInfo)
        lib.ngSpice_AllPlots.restype = POINTER(c_char_p)
        lib.ngSpice_AllVecs.argtypes = (c_char_p,)
        lib.ngSpice_AllVecs.restype = POINTER(c_char_p)
        lib.ngSpice_running.restype = c_bool
        send_char, send_stat, controlled_exit, bg_running = self._callbacks
        lib.ngSpice_Init(send_char, send_stat, controlled_exit, None, None, bg_running, None)
        self._lib = lib
        self._exited = False
        self._has_circuit = False

    def _reload(self) -> None:
        _ctypes.dlclose(self._lib._handle)
        self._load()

    def _on_char(self, text: bytes | None, _ident: int, _user: int | None) -> int:
        if text is not None:
            self._output.append(text.decode("utf-8", "replace"))
        return 0

    def _on_stat(self, text: bytes | None, _ident: int, _user: int | None) -> int:
        """ngspice's status line ("tran: 34.5%") → the run's progress callback (0..1)."""
        if text is not None and self._progress is not None and self._stopped is None:
            found = _PERCENT.search(text.decode("utf-8", "replace"))
            if found:
                try:
                    self._progress(min(1.0, float(found[1]) / 100))
                except Exception as err:  # the caller wants the run stopped (a cancel)
                    self._stopped = err
                    self._finished.set()
        return 0

    def _on_background(self, not_running: bool, _ident: int, _user: int | None) -> int:
        if not_running:
            self._finished.set()
        return 0

    def _on_exit(self, status: int, _immediate: bool, _quit: bool, _ident: int, _u: int) -> int:
        self._exited = True
        self._output.append(f"stderr ngspice requested exit (status {status})")
        return status

    def _command(self, command: str) -> int:
        return int(self._lib.ngSpice_Command(command.encode()))

    def _read_version(self) -> str:
        self._output.clear()
        self._command("version -s")
        for line in self._output:
            if "ngspice-" in line:
                return line.split("ngspice-", 1)[1].split()[0]
        return "unknown"

    def version(self) -> str:
        return self._version

    def run(
        self,
        netlist: str,
        timeout: float | None = DEFAULT_TIMEOUT,
        progress: Callable[[float], None] | None = None,
    ) -> SimResult:
        with self._lock:
            if self._stuck and self._lib.ngSpice_running():
                raise EngineStuck(STUCK_SINCE)
            self._stuck = False  # it stopped in the end
            self._progress = progress
            try:
                return self._run_locked(netlist, timeout)
            finally:
                self._progress = None
                if self._exited:
                    self._reload()

    def _run_locked(self, netlist: str, timeout: float | None) -> SimResult:
        self._output.clear()
        if self._has_circuit:
            self._command("destroy all")
            self._command("remcirc")
            self._has_circuit = False
        lines = prepare_netlist(netlist)
        array = (c_char_p * (len(lines) + 1))(*(ln.encode() for ln in lines), None)
        self._lib.ngSpice_Circ(array)
        self._has_circuit = True
        self._raise_on_errors("The circuit couldn't be loaded into the simulator.")
        self._run_in_background(timeout)
        self._raise_on_errors("The simulation failed.")
        plots = [self._read_plot(name) for name in self._plot_names()]
        log = list(self._output)
        if not plots:
            raise SimError("The simulation produced no results.", log)
        return SimResult(plots=plots, log=log)

    def _run_in_background(self, timeout: float | None) -> None:
        """`bg_run`, waiting at most `timeout` seconds; `bg_halt` and SimError if it's late.
        If the progress callback raises, the run is halted and that exception raised."""
        self._stopped = None
        self._finished.clear()
        self._command("bg_run")
        if self._finished.wait(timeout) and self._stopped is None:
            return
        self._command("bg_halt")
        deadline = time.monotonic() + HALT_WAIT
        while self._lib.ngSpice_running() and time.monotonic() < deadline:
            time.sleep(0.001)
        # Some DC solves never look at the halt (D-195). ngspice's thread is then still
        # in that solve, and every later run would wait behind it for its whole timeout.
        self._stuck = bool(self._lib.ngSpice_running())
        if self._stopped is not None:
            raise self._stopped
        if self._stuck:
            raise EngineStuck(STUCK_ON_THIS)
        raise SimTimeout(
            f"The simulation took longer than {timeout:g} s and was stopped. Try a shorter "
            "time span, or check the circuit for a part with an extreme value.",
            timeout or 0.0,
            list(self._output),
        )

    def _raise_on_errors(self, message: str) -> None:
        errors = [ln for ln in self._output if is_error_line(ln)]
        if errors or self._exited:
            raise SimError(message, list(self._output))

    def _plot_names(self) -> list[str]:
        # Every run starts with "destroy all", so these are this run's plots, plus
        # the permanent "const" plot.
        return [n for n in _string_array(self._lib.ngSpice_AllPlots()) if n != "const"]

    def _read_plot(self, plot: str) -> Plot:
        vectors: dict[str, Vector] = {}
        for vec in _string_array(self._lib.ngSpice_AllVecs(plot.encode())):
            info = self._lib.ngGet_Vec_Info(f"{plot}.{vec}".encode())
            if info:
                vectors[vec.lower()] = _to_array(info.contents)
        return Plot(name=plot, vectors=vectors)


def _string_array(ptr: "ctypes._Pointer[c_char_p]") -> list[str]:
    out: list[str] = []
    if not ptr:
        return out
    i = 0
    while (item := ptr[i]) is not None:
        out.append(item.decode())
        i += 1
    return out


def _to_array(info: _VectorInfo) -> Vector:
    n = info.v_length
    if n == 0:
        return np.zeros(0)
    if info.v_flags & _VF_COMPLEX:
        raw = np.ctypeslib.as_array(info.v_compdata, shape=(n,))
        return raw["cx_real"] + 1j * raw["cx_imag"]
    return np.ctypeslib.as_array(info.v_realdata, shape=(n,)).copy()
