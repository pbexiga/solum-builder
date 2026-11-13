import shutil
import threading
from pathlib import Path

import numpy as np
import pytest

from solum.cache import CachedEngine, SimCache, content_hash, result_from_bytes, result_to_bytes
from solum.sim.engine import Plot, SimResult


class CountingEngine:
    name = "fake"

    def __init__(self) -> None:
        self.runs = 0

    def version(self) -> str:
        return "1"

    def run(self, netlist: str, timeout: float | None = None, progress: object = None) -> SimResult:
        self.runs += 1
        return SimResult([Plot("ac1", {"frequency": np.array([10.0, 20.0]),
                                       "out": np.array([1 + 1j, 0.5j])})],
                         log=[f"ran {netlist}"])  # fmt: skip


def test_hash_separates_parts() -> None:
    assert content_hash("ab", "c") != content_hash("a", "bc")
    assert content_hash("x") == content_hash(b"x")
    assert len(content_hash("x")) == 64


def test_result_round_trip() -> None:
    r = SimResult([Plot("op1", {"@q1[ic]": np.array([1e-3]), "v1#branch": np.array([2.0])}),
                   Plot("ac1", {"out": np.array([1 + 2j])})], log=["hi"])  # fmt: skip
    back = result_from_bytes(result_to_bytes(r))
    assert [p.name for p in back.plots] == ["op1", "ac1"]
    assert back.plot("op").vectors["@q1[ic]"][0] == 1e-3
    assert back.plot("ac").vectors["out"][0] == 1 + 2j
    assert back.log == ["hi"]


def test_second_run_is_a_hit(tmp_path: Path) -> None:
    inner = CountingEngine()
    engine = CachedEngine(inner, SimCache(tmp_path, max_bytes=10**6))
    first = engine.run("netlist A")
    second = engine.run("netlist A")
    engine.run("netlist B")
    assert inner.runs == 2
    assert (engine.hits, engine.misses) == (1, 2)
    assert second.plot("ac").vectors["out"] == pytest.approx(first.plot("ac").vectors["out"])


def test_a_netlist_already_running_is_waited_for_not_run_again(tmp_path: Path) -> None:
    """D-095: a second request for a netlist that's running waits for its result."""
    started = threading.Event()
    release = threading.Event()

    class SlowEngine(CountingEngine):
        def run(
            self, netlist: str, timeout: float | None = None, progress: object = None
        ) -> SimResult:
            started.set()
            release.wait(5)
            return super().run(netlist, timeout, progress)

    inner = SlowEngine()
    engine = CachedEngine(inner, SimCache(tmp_path, max_bytes=10**6))
    first = threading.Thread(target=engine.run, args=("slow",))
    first.start()
    assert started.wait(5)
    second = threading.Thread(target=engine.run, args=("slow",))
    second.start()
    release.set()
    first.join(5)
    second.join(5)
    assert inner.runs == 1
    assert (engine.hits, engine.misses) == (1, 1)


def test_a_repeated_result_is_unpacked_once(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """D-273: a hit on a recent result comes from memory, not unpacked from disk again."""
    import solum.cache as module

    unpacked = []
    real = module.result_from_bytes
    monkeypatch.setattr(module, "result_from_bytes", lambda d: unpacked.append(1) or real(d))
    cache = SimCache(tmp_path, max_bytes=10**6)
    engine = CachedEngine(CountingEngine(), cache)
    first = engine.run("n")
    assert engine.run("n") is first and engine.run("n") is first
    assert unpacked == [] and (engine.hits, engine.misses) == (2, 1)
    with pytest.raises(ValueError, match="read-only"):  # shared, so it can't be changed
        first.plot("ac").vectors["out"][0] = 0
    other = CachedEngine(CountingEngine(), cache)  # another engine on the folder: from disk
    assert other.run("n").log == first.log and unpacked == [1]
    assert other.run("n").log == first.log and unpacked == [1]


def test_recent_results_stay_within_their_memory(tmp_path: Path) -> None:
    one = sum(v.nbytes for v in CountingEngine().run("x").plots[0].vectors.values())
    engine = CachedEngine(CountingEngine(), SimCache(tmp_path, 10**6), recent_bytes=2 * one)
    a = engine.run("a")
    engine.run("b")
    engine.run("a")  # a is now the most recent
    engine.run("c")  # so b makes room
    assert engine.run("a") is a
    assert list(engine._recent) == [engine.key("c"), engine.key("a")]
    small = CachedEngine(CountingEngine(), SimCache(tmp_path, 10**6), recent_bytes=one - 1)
    small.run("d")
    assert not small._recent  # too big to hold: the disk cache still answers
    assert small.run("d").log == ["ran d"] and small.hits == 1


def test_safe_to_delete(tmp_path: Path) -> None:
    inner = CountingEngine()
    cache = SimCache(tmp_path / "cache", max_bytes=10**6)
    engine = CachedEngine(inner, cache)
    engine.run("n")
    for blob in (tmp_path / "cache").rglob("*.bin"):
        blob.unlink()  # blobs gone, index says present: a miss, not an error
    engine.run("n")
    (tmp_path / "cache" / "index.sqlite").unlink()  # index gone: rebuilt empty
    engine.run("n")
    assert inner.runs == 3


def test_the_whole_cache_deleted_while_open(tmp_path: Path) -> None:
    """The index connection is kept open; deleting the folder under it starts afresh,
    and what's written next is in the new index (a later process finds it)."""
    inner = CountingEngine()
    engine = CachedEngine(inner, SimCache(tmp_path / "cache", max_bytes=10**6))
    engine.run("n")
    shutil.rmtree(tmp_path / "cache")
    engine.run("n")
    assert inner.runs == 2
    assert SimCache(tmp_path / "cache", max_bytes=10**6).has(engine.key("n"))


def test_two_caches_on_one_folder_share_it(tmp_path: Path) -> None:
    """The server and a render worker each hold their own connection to the index."""
    server, worker = SimCache(tmp_path, 10_000), SimCache(tmp_path, 10_000)
    worker.put_bytes("wav", b"RIFF")
    assert server.get_bytes("wav") == b"RIFF"
    server.forget("wav")
    assert not worker.has("wav")


def test_evicts_least_recently_used(tmp_path: Path) -> None:
    limit = [10**6]
    cache = SimCache(tmp_path, max_bytes=lambda: limit[0])  # a size that changes (D-310)
    engine = CachedEngine(CountingEngine(), cache)
    engine.run("a")
    one = cache.size()
    limit[0] = int(one * 2.5)
    engine.run("b")
    engine.run("a")  # touch a: b is now the oldest
    engine.run("c")
    assert cache.size() <= cache.max_bytes
    assert cache.get(engine.key("b")) is None
    assert cache.get(engine.key("a")) is not None
    assert cache.get(engine.key("c")) is not None
    # a smaller size holds as soon as the cache is trimmed, the oldest going first
    limit[0] = int(one * 1.5)
    cache.trim()
    assert cache.size() == one
    assert cache.get(engine.key("a")) is None
    assert cache.get(engine.key("c")) is not None


def test_bytes_blobs_share_the_index(tmp_path: Path) -> None:
    cache = SimCache(tmp_path, max_bytes=10_000)
    assert cache.get_bytes("k") is None and not cache.has("k")
    cache.put_bytes("k", b"RIFF audio")
    assert cache.has("k") and cache.get_bytes("k") == b"RIFF audio"
    assert cache.size() == len(b"RIFF audio")
    cache.forget("k")
    assert cache.get_bytes("k") is None and cache.size() == 0


def test_a_missing_blob_is_a_miss(tmp_path: Path) -> None:
    cache = SimCache(tmp_path, max_bytes=10_000)
    cache.put_bytes("k", b"x")
    for blob in tmp_path.rglob("*.bin"):
        blob.unlink()
    assert not cache.has("k") and cache.get_bytes("k") is None


def test_the_same_result_written_at_once_by_several_requests(tmp_path: Path) -> None:
    """Two identical requests finishing together both write the blob (a 500 before: they
    shared one temp file, and the second rename found it gone)."""
    cache = SimCache(tmp_path, max_bytes=10_000_000)
    data = b"x" * 200_000
    start = threading.Barrier(8)
    errors: list[BaseException] = []

    def write() -> None:
        start.wait()
        try:
            for _ in range(20):
                cache.put_bytes("same", data)
        except BaseException as err:
            errors.append(err)

    threads = [threading.Thread(target=write) for _ in range(8)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    assert errors == []
    assert cache.get_bytes("same") == data
    assert not list(tmp_path.rglob("*.tmp"))  # no temp files left behind
