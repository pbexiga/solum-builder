"""User circuits in DATA_DIR with the SQLite search index in CACHE_DIR."""

import os
from collections.abc import Callable
from pathlib import Path

import pytest

from solum.circuit.build import CircuitBuilder
from solum.circuit.io import load_circuit
from solum.circuit.schema import Circuit, Version
from solum.store import (
    CircuitEntry,
    CircuitStore,
    StoreError,
    current_ids,
    file_id,
    link_id,
    matches,
    part_models,
    resolve_id,
    split_id,
    strip_version,
)


@pytest.fixture
def store(tmp_path: Path) -> CircuitStore:
    return CircuitStore(tmp_path / "data", tmp_path / "cache")


@pytest.fixture
def fuzz(circuit: Callable[[str], CircuitBuilder]) -> Circuit:
    c = (
        circuit("Fuzz")
        .part("Q1", "bjt", "c", "b", "GND", model="AC128")
        .part("Q2", "bjt", "out", "c", "GND", model="2N5089")
        .part("R1", "resistor", "c", "V+", value="33k")
        .build()
    )
    return c.model_copy(update={"tags": ["germanium", "fuzz"]})


def test_part_models_are_sorted_and_unique(fuzz: Circuit) -> None:
    assert part_models(fuzz) == ["2N5089", "AC128"]


@pytest.mark.parametrize(
    ("query", "hit"),
    [("", True), ("FUZZ", True), ("germ", True), ("ac128", True), ("2n5089", True), ("rat", False)],
)
def test_matches_name_tag_or_model(query: str, hit: bool) -> None:
    entry = CircuitEntry("f", "Fuzz Face mine", ["germanium"], ["AC128", "2N5089"])
    assert matches(entry, query) is hit


def test_create_save_load_round_trip(store: CircuitStore, fuzz: Circuit) -> None:
    created = store.create(fuzz, "My Fuzz")
    assert (created.id, created.name, created.starter) == ("my-fuzz-v1", "My Fuzz", False)
    assert str(created.version) == "v1.0"
    assert store.load("my-fuzz-v1") == created
    assert store.load("my-fuzz") == created  # the short id finds the current version
    assert [(e.id, e.current) for e in store.entries()] == [("my-fuzz-v1", True)]


def test_entries_say_when_each_file_was_saved(store: CircuitStore, fuzz: Circuit) -> None:
    """Open's Recent section sorts on it: the file's time, UTC, to the millisecond."""
    store.create(fuzz, "Old")
    store.create(fuzz, "New")
    os.utime(store.path("old-v1"), (1_700_000_000.25, 1_700_000_000.25))
    os.utime(store.path("new-v1"), (1_700_000_000.75, 1_700_000_000.75))
    assert {e.id: e.saved for e in store.entries()} == {
        "old-v1": "2023-11-14T22:13:20.250+00:00",
        "new-v1": "2023-11-14T22:13:20.750+00:00",
    }


def test_a_save_that_changes_something_adds_one_to_the_minor(
    store: CircuitStore, fuzz: Circuit
) -> None:
    created = store.create(fuzz, "Fuzz")
    assert store.save(created) == created  # nothing changed: same tag, file untouched
    once = store.save(created.with_part("R1", value="47k"))
    twice = store.save(once.with_part("R1", value="22k"))
    assert (str(once.version), str(twice.version)) == ("v1.1", "v1.2")
    assert str(store.load("fuzz").version) == "v1.2"
    assert [e.version for e in store.entries()] == ["v1.2"]
    # the tag the editor sends is ignored: the store counts
    sent = twice.model_copy(update={"version": created.version, "tags": ["x"]})
    assert str(store.save(sent).version) == "v1.3"


def test_saving_a_new_name_renames_the_file(store: CircuitStore, fuzz: Circuit) -> None:
    created = store.create(fuzz, "My Fuzz")
    store.create(fuzz, "Other")
    renamed = store.save(created.model_copy(update={"name": "Fuzz, renamed "}))
    assert (renamed.id, renamed.name, str(renamed.version)) == (
        "fuzz-renamed-v1",
        "Fuzz, renamed",
        "v1.1",
    )
    assert not store.path("my-fuzz-v1").exists()
    assert [e.id for e in store.entries()] == ["fuzz-renamed-v1", "other-v1"]
    with pytest.raises(StoreError, match="already have a circuit called Other"):
        store.save(renamed.model_copy(update={"name": "OTHER"}))


def test_create_never_overwrites(store: CircuitStore, fuzz: Circuit) -> None:
    store.create(fuzz, "Fuzz")
    with pytest.raises(
        StoreError, match=r"already have a circuit called Fuzz \(its file is fuzz-v1.json\)"
    ):
        store.create(fuzz, "fuzz!")
    assert len(store.entries()) == 1


def test_update_info_renames_describes_and_tags(store: CircuitStore, fuzz: Circuit) -> None:
    store.create(fuzz, "Fuzz")
    store.create(fuzz, "Taken")
    c = store.update_info("fuzz", name="Big Fuzz", description="mine", tags=["a"])
    assert (c.id, c.name, c.description, c.tags, str(c.version)) == (
        "big-fuzz-v1", "Big Fuzz", "mine", ["a"], "v1.1"
    )  # fmt: skip
    assert not store.path("fuzz-v1").exists() and store.load("big-fuzz") == c
    assert store.update_info("big-fuzz", name="Big Fuzz") == c  # no change, no bump
    assert store.update_info("big-fuzz", name="big fuzz").id == "big-fuzz-v1"  # same file
    with pytest.raises(StoreError, match="already have a circuit called Taken"):
        store.update_info("big-fuzz", name="Taken")
    with pytest.raises(StoreError, match="Give the circuit a name"):
        store.update_info("big-fuzz", name=" ")


def test_final_versions_are_read_only_until_unlocked(store: CircuitStore, fuzz: Circuit) -> None:
    c = store.create(fuzz, "Fuzz")
    locked = store.update_info("fuzz", final=True)
    assert (locked.final, str(locked.version)) == (True, "v1.0")  # locking isn't a change
    assert [e.final for e in store.entries()] == [True]
    with pytest.raises(StoreError, match="Fuzz is a final version, so it's read-only"):
        store.save(c.with_part("R1", value="1k"))
    with pytest.raises(StoreError, match="final version"):
        store.update_info("fuzz", description="x")
    open_again = store.update_info("fuzz", final=False, description="fixed")  # unlock + change
    assert (open_again.final, open_again.description, str(open_again.version)) == (
        False,
        "fixed",
        "v1.1",
    )
    assert str(store.save(open_again.with_part("R1", value="1k")).version) == "v1.2"


def test_new_major_marks_the_current_final_and_carries_on(
    store: CircuitStore, fuzz: Circuit
) -> None:
    c = store.create(fuzz, "Muff stage")
    c = store.save(c.with_part("R1", value="47k"))  # v1.1
    current, final = store.new_major("muff-stage")
    assert (current.id, current.name, str(current.version), current.final) == (
        "muff-stage-v2", "Muff stage", "v2.0", False
    )  # fmt: skip
    assert (final.id, final.name, str(final.version), final.final) == (
        "muff-stage-v1", "Muff stage", "v1.1", True
    )  # fmt: skip
    assert final.parts == c.parts == current.parts
    assert [(e.id, e.version, e.final, e.current) for e in store.entries()] == [
        ("muff-stage-v2", "v2.0", False, True), ("muff-stage-v1", "v1.1", True, False)
    ]  # fmt: skip
    assert store.load("muff-stage") == current
    with pytest.raises(StoreError, match="There's a newer version of Muff stage"):
        store.new_major("muff-stage-v1")
    # a fix to v1 after v2 exists: unlock, change, it counts on in v1
    fixed = store.update_info("muff-stage-v1", final=False)
    assert str(store.save(fixed.with_part("R1", value="1k")).version) == "v1.2"
    # the current one marked final without a new major: still current, and v3 can follow
    store.update_info("muff-stage", final=True)
    assert store.entries()[0].current
    current, final = store.new_major("muff-stage")
    assert (current.id, str(current.version), final.id, final.final) == (
        "muff-stage-v3", "v3.0", "muff-stage-v2", True
    )  # fmt: skip


def test_renaming_renames_every_version(store: CircuitStore, fuzz: Circuit) -> None:
    store.create(fuzz, "Muff stage")
    store.new_major("muff-stage")
    renamed = store.update_info("muff-stage", name="Big Muff stage")
    assert (renamed.id, str(renamed.version)) == ("big-muff-stage-v2", "v2.1")
    assert [(e.id, e.name, e.version, e.final) for e in store.entries()] == [
        ("big-muff-stage-v2", "Big Muff stage", "v2.1", False),
        ("big-muff-stage-v1", "Big Muff stage", "v1.0", True),  # a final keeps its tag
    ]
    saved = store.save(renamed.model_copy(update={"name": "Muff"}))
    assert saved.id == "muff-v2"
    assert sorted(store.ids()) == ["muff-v1", "muff-v2"]


def test_a_name_belongs_to_every_version_and_has_no_version(
    store: CircuitStore, fuzz: Circuit
) -> None:
    store.create(fuzz, "Fuzz")
    store.new_major("fuzz")
    store.delete("fuzz-v2")  # only v1 left: the name is still taken
    with pytest.raises(StoreError, match=r"called Fuzz \(its file is fuzz-v1.json\)"):
        store.create(fuzz, "Fuzz")
    with pytest.raises(StoreError, match="Leave the version out of the name"):
        store.create(fuzz, "Rat v2")
    assert store.create(fuzz, "Rat 2").id == "rat-2-v1"


def test_old_file_names_are_tidied_when_listed(store: CircuitStore, fuzz: Circuit) -> None:
    """Files from before D-076: `fuzz.json` at v2, and its final copy `fuzz-v1.json`
    called "Fuzz v1"; a file dropped in by hand with any name."""
    store.dir.mkdir(parents=True)
    store._write(fuzz.model_copy(update={"id": "fuzz", "version": Version(major=2, minor=3)}))
    store._write(fuzz.model_copy(update={"id": "fuzz-v1", "name": "Fuzz v1", "final": True}))
    store._write(fuzz.model_copy(update={"id": "x", "name": "Rat"}))
    (store.dir / "broken.json").write_text("{ nope")
    found = [(e.id, e.name, e.version, e.current) for e in store.entries() if not e.problem]
    assert found == [
        ("fuzz-v2", "Fuzz", "v2.3", True),
        ("fuzz-v1", "Fuzz", "v1.0", False),
        ("rat-v1", "Rat", "v1.0", True),
    ]
    assert load_circuit(store.dir / "fuzz-v2.json").id == "fuzz-v2"
    assert sorted(store.ids()) == ["broken", "fuzz-v1", "fuzz-v2", "rat-v1"]


def test_version_ids() -> None:
    assert file_id("test-block", 2) == "test-block-v2"
    assert split_id("test-block-v12") == ("test-block", 12)
    assert split_id("fuzz-v2-v1") == ("fuzz-v2", 1)
    assert split_id("test-block") == ("test-block", None)
    ids = ["a-v1", "a-v2", "a-v10", "b-v1", "legacy"]
    assert resolve_id(ids, "a") == "a-v10"  # by number, not text
    assert resolve_id(ids, "a-v2") == "a-v2"
    assert resolve_id(ids, "c") is None
    assert current_ids(ids) == {"a-v10", "b-v1", "legacy"}
    assert (link_id("a-v10", ids), link_id("a-v2", ids)) == ("a", "a-v2")
    assert strip_version("Fuzz v1", 1) == "Fuzz"
    assert strip_version("Fuzz V2 ", 2) == "Fuzz"
    assert strip_version("Fuzz v2", 1) == "Fuzz v2"


def test_create_from_starter_clears_the_flag(store: CircuitStore, fuzz: Circuit) -> None:
    starter = fuzz.model_copy(update={"starter": True})
    assert store.create(starter).starter is False


def test_create_needs_a_name(store: CircuitStore, fuzz: Circuit) -> None:
    with pytest.raises(StoreError, match="Give the circuit a name"):
        store.create(fuzz, "  ")


def test_search_by_name_tag_and_model(store: CircuitStore, fuzz: Circuit) -> None:
    store.create(fuzz, "Fuzz Face")
    plain = fuzz.model_copy(update={"tags": [], "parts": fuzz.parts[2:]})
    store.create(plain, "Divider")
    assert [e.name for e in store.entries()] == ["Divider", "Fuzz Face"]
    assert [e.name for e in store.entries("germanium")] == ["Fuzz Face"]
    assert [e.name for e in store.entries("2n5089")] == ["Fuzz Face"]
    assert [e.name for e in store.entries("divid")] == ["Divider"]
    assert store.entries("nothing like it") == []


def test_index_follows_files_changed_outside(store: CircuitStore, fuzz: Circuit) -> None:
    created = store.create(fuzz, "Fuzz")
    path = store.path(created.id)
    text = path.read_text().replace('"Fuzz"', '"Edited by hand"')
    path.write_text(text)
    os.utime(path, ns=(1, 1))  # a different mtime even on coarse clocks
    assert [(e.id, e.name) for e in store.entries()] == [("edited-by-hand-v1", "Edited by hand")]
    assert not path.exists()  # the file follows the name
    store.path("edited-by-hand-v1").unlink()
    assert store.entries() == []


def test_index_is_safe_to_delete(store: CircuitStore, fuzz: Circuit, tmp_path: Path) -> None:
    store.create(fuzz, "Fuzz")
    (tmp_path / "cache" / "index.sqlite").unlink()
    assert [e.name for e in store.entries("germanium")] == ["Fuzz"]


def test_broken_file_is_listed_with_its_problem(store: CircuitStore) -> None:
    store.dir.mkdir(parents=True)
    (store.dir / "broken.json").write_text("{ nope")
    (entry,) = store.entries()
    assert entry.id == "broken"
    assert entry.problem is not None and "isn't valid JSON" in entry.problem


def test_missing_and_bad_ids(store: CircuitStore) -> None:
    with pytest.raises(StoreError, match="no saved circuit called 'nope'"):
        store.load("nope")
    with pytest.raises(StoreError, match="isn't a circuit id"):
        store.load("../etc/passwd")


def test_saved_file_is_a_normal_circuit_file(store: CircuitStore, fuzz: Circuit) -> None:
    created = store.create(fuzz, "Fuzz")
    assert load_circuit(store.dir / "fuzz-v1.json") == created


def test_delete_removes_file_and_row(store: CircuitStore, fuzz: Circuit) -> None:
    store.create(fuzz, "Fuzz")
    store.create(fuzz, "Other")
    store.delete("fuzz")
    assert not (store.dir / "fuzz-v1.json").exists()
    assert [e.id for e in store.entries()] == ["other-v1"]
    with pytest.raises(StoreError, match="no saved circuit called 'fuzz'"):
        store.delete("fuzz")
    with pytest.raises(StoreError, match="isn't a circuit id"):
        store.delete("../x")
