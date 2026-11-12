"""Content-hash cache for simulation results and rendered audio (SQLite index + blob files
in CACHE_DIR).

The key covers everything that decides a result: the full netlist text (circuit, models,
analysis) and the engine name and version. Everything here is safe to delete at any
time: a missing index is rebuilt empty, a missing blob is a miss.
"""

import hashlib
import io
import json
import os
import sqlite3
import tempfile
import threading
import time
from collections import OrderedDict
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from pathlib import Path

import numpy as np

from solum.config import Settings
from solum.sim.engine import DEFAULT_TIMEOUT, Plot, SimEngine, SimResult


def content_hash(*parts: str | bytes) -> str:
    """SHA-256 over the parts, each length-prefixed so ("ab", "c") != ("a", "bc")."""
    h = hashlib.sha256()
    for part in parts:
        data = part.encode() if isinstance(part, str) else part
        h.update(len(data).to_bytes(8, "big"))
        h.update(data)
    return h.hexdigest()


def result_to_bytes(result: SimResult) -> bytes:
    manifest = {"plots": [{"name": p.name, "vectors": list(p.vectors)} for p in result.plots],
                "log": result.log}  # fmt: skip
    arrays = {f"a{i}": v for i, v in enumerate(v for p in result.plots for v in p.vectors.values())}
    buf = io.BytesIO()
    np.savez(buf, manifest=np.array(json.dumps(manifest)), **arrays)  # type: ignore[arg-type]
    return buf.getvalue()


def result_from_bytes(data: bytes) -> SimResult:
    with np.load(io.BytesIO(data), allow_pickle=False) as npz:
        manifest = json.loads(str(npz["manifest"]))
        arrays = iter(npz[f"a{i}"] for i in range(len(npz.files) - 1))
        plots = [Plot(p["name"], {name: next(arrays) for name in p["vectors"]})
                 for p in manifest["plots"]]  # fmt: skip
    return SimResult(plots=plots, log=manifest["log"])


class SimCache:
    """Results by key, least-recently-used eviction above `max_bytes`."""

    def __init__(self, cache_dir: Path, max_bytes: int) -> None:
        self.dir = cache_dir
        self.max_bytes = max_bytes
        self._lock = threading.Lock()
        self._conn: sqlite3.Connection | None = None
        self._pid = 0

    @contextmanager
    def _db(self) -> Iterator[sqlite3.Connection]:
        """The index, one transaction. One connection per process, kept open: opening one
        per call made every commit and close sync to disk (~10 ms each on btrfs; a
        find-parts search makes thousands, 45 s instead of 5). WAL with synchronous
        NORMAL keeps it whole through a crash without that. Reopened if the cache was
        deleted while the app ran. Callers hold `_lock`."""
        path = self.dir / "index.sqlite"
        if self._conn is None or self._pid != os.getpid() or not path.exists():
            self.dir.mkdir(parents=True, exist_ok=True)
            self._conn = sqlite3.connect(path, timeout=30, check_same_thread=False)
            self._pid = os.getpid()
            self._conn.execute("PRAGMA journal_mode = WAL")
            self._conn.execute("PRAGMA synchronous = NORMAL")
            self._conn.execute(
                "CREATE TABLE IF NOT EXISTS sim_cache (key TEXT PRIMARY KEY, bytes INTEGER "
                "NOT NULL, last_used REAL NOT NULL)"
            )
        with self._conn:
            yield self._conn

    def _blob(self, key: str) -> Path:
        return self.dir / "sim" / key[:2] / f"{key}.bin"

    def get(self, key: str) -> SimResult | None:
        data = self.get_bytes(key)
        if data is None:
            return None
        try:
            return result_from_bytes(data)
        except (OSError, ValueError, KeyError):
            self.forget(key)
            return None

    def put(self, key: str, result: SimResult) -> None:
        self.put_bytes(key, result_to_bytes(result))

    def forget(self, key: str) -> None:
        with self._lock, self._db() as db:
            db.execute("DELETE FROM sim_cache WHERE key = ?", (key,))
            self._blob(key).unlink(missing_ok=True)

    def get_bytes(self, key: str) -> bytes | None:
        """Any cached blob (a simulation result, a rendered WAV) by key, or None."""
        with self._lock, self._db() as db:
            if db.execute("SELECT 1 FROM sim_cache WHERE key = ?", (key,)).fetchone() is None:
                return None
            try:
                data = self._blob(key).read_bytes()
            except OSError:
                db.execute("DELETE FROM sim_cache WHERE key = ?", (key,))
                return None
            db.execute("UPDATE sim_cache SET last_used = ? WHERE key = ?", (time.time(), key))
            return data

    def touch(self, key: str) -> bool:
        """True if `key` is cached, marking it used now: what a read does, without the
        read (for a result already held in memory, `CachedEngine`)."""
        with self._lock, self._db() as db:
            if not self._blob(key).exists():
                return False
            done = db.execute(
                "UPDATE sim_cache SET last_used = ? WHERE key = ?", (time.time(), key)
            )
            return done.rowcount == 1

    def has(self, key: str) -> bool:
        with self._lock, self._db() as db:
            found = db.execute("SELECT 1 FROM sim_cache WHERE key = ?", (key,)).fetchone()
        return found is not None and self._blob(key).exists()

    def put_bytes(self, key: str, data: bytes) -> None:
        blob = self._blob(key)
        blob.parent.mkdir(parents=True, exist_ok=True)
        # a temp file of its own: identical requests may finish at the same moment, in
        # threads or worker processes, and each rename is atomic
        fd, name = tempfile.mkstemp(dir=blob.parent, prefix=f"{key}.", suffix=".tmp")
        with os.fdopen(fd, "wb") as f:
            f.write(data)
        Path(name).replace(blob)
        with self._lock, self._db() as db:
            db.execute("INSERT OR REPLACE INTO sim_cache VALUES (?, ?, ?)",
                       (key, len(data), time.time()))  # fmt: skip
            self._evict(db)

    def _evict(self, db: sqlite3.Connection) -> None:
        total = db.execute("SELECT COALESCE(SUM(bytes), 0) FROM sim_cache").fetchone()[0]
        if total <= self.max_bytes:
            return
        rows = db.execute("SELECT key, bytes FROM sim_cache ORDER BY last_used").fetchall()
        for key, size in rows:
            if total <= self.max_bytes:
                break
            self._blob(key).unlink(missing_ok=True)
            db.execute("DELETE FROM sim_cache WHERE key = ?", (key,))
            total -= size

    def size(self) -> int:
        with self._lock, self._db() as db:
            return int(db.execute("SELECT COALESCE(SUM(bytes), 0) FROM sim_cache").fetchone()[0])


RECENT_BYTES = 64_000_000  # results a CachedEngine also holds in memory, most recent first


def cache_from_settings(settings: Settings) -> SimCache:
    """The app's cache: `CACHE_DIR`, up to `CACHE_MAX_GB`. One per process is enough: the
    server's simulator, API and render jobs share theirs; each render worker has its own."""
    return SimCache(settings.cache_dir, max_bytes=int(settings.cache_max_gb * 1e9))


def result_bytes(result: SimResult) -> int:
    """The memory a result's vectors take."""
    return sum(v.nbytes for p in result.plots for v in p.vectors.values())


class CachedEngine:
    """A SimEngine that answers repeated netlists from the cache. Counts hits and misses.
    One netlist runs at a time (the engine is one ngspice anyway): a request that arrives
    while the same netlist is running waits for that run's result instead of running it
    again (Problems and Run ask for the same operating point at once, D-095).

    The most recent results are also held in memory, up to `recent_bytes` (D-273): a
    search reads the same operating point hundreds of times, and unpacking it from disk
    each time took half its run. The disk cache still decides what is cached (a result
    deleted there is run again), so the memory copy only saves the unpacking. Results are
    shared between callers, so their vectors are read-only."""

    def __init__(
        self, engine: SimEngine, cache: SimCache, recent_bytes: int = RECENT_BYTES
    ) -> None:
        self.engine = engine
        self.cache = cache
        self.name = engine.name
        self.hits = 0
        self.misses = 0
        self.recent_bytes = recent_bytes
        self._running = threading.Lock()
        self._recent: OrderedDict[str, SimResult] = OrderedDict()
        self._recent_size = 0
        self._recent_lock = threading.Lock()

    def _get(self, key: str) -> SimResult | None:
        with self._recent_lock:
            kept = self._recent.get(key)
        if kept is not None and self.cache.touch(key):
            with self._recent_lock:
                if key in self._recent:
                    self._recent.move_to_end(key)
            return kept
        found = self.cache.get(key)
        if found is not None:
            self._keep(key, found)
        return found

    def _keep(self, key: str, result: SimResult) -> None:
        for plot in result.plots:
            for vector in plot.vectors.values():
                vector.flags.writeable = False
        size = result_bytes(result)
        with self._recent_lock:
            if key in self._recent:
                self._recent_size -= result_bytes(self._recent.pop(key))
            if size > self.recent_bytes:
                return
            self._recent[key] = result
            self._recent_size += size
            while self._recent_size > self.recent_bytes:
                _, old = self._recent.popitem(last=False)
                self._recent_size -= result_bytes(old)

    def version(self) -> str:
        return self.engine.version()

    def key(self, netlist: str) -> str:
        return content_hash(self.engine.name, self.engine.version(), netlist)

    def run(
        self,
        netlist: str,
        timeout: float | None = DEFAULT_TIMEOUT,
        progress: Callable[[float], None] | None = None,
    ) -> SimResult:
        key = self.key(netlist)
        cached = self._get(key)
        if cached is not None:
            self.hits += 1
            return cached
        with self._running:
            cached = self._get(key)  # it may have run while this waited
            if cached is not None:
                self.hits += 1
                return cached
            self.misses += 1
            result = self.engine.run(netlist, timeout=timeout, progress=progress)
            self.cache.put(key, result)
            self._keep(key, result)
            return result
