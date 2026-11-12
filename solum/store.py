"""The user's circuits: JSON files in `DATA_DIR/circuits/` (the source of truth, D-008)
with a search index in `CACHE_DIR/index.sqlite`. The same store holds My Blocks in
`DATA_DIR/blocks/` (`kind="blocks"`, D-072), indexed in a table of their own.

The index holds each file's name, tags and part models, plus its size and modification
time so a changed file is re-read. `sync()` runs on start and before every listing, so
the index is safe to delete at any time and files edited outside the app show up.

Every file has a version tag (`v1.12`): a save that changes the file adds one to the
minor. Each major version is a file of its own, `<name>-v<major>.json` (D-076): all
versions share the name, and the newest major is the current one, which the short id
(`<name>`) finds. A new major version marks the file final (read-only until unlocked)
and carries on in the next one. Renaming renames every version's file, and a name
another circuit has is refused (D-075, D-076).
"""

import json
import re
import sqlite3
import threading
from collections.abc import Iterable, Iterator
from contextlib import contextmanager
from dataclasses import dataclass, field, replace
from datetime import UTC, datetime
from pathlib import Path
from typing import Literal, Protocol

from solum.circuit.dismissals import kept_dismissals
from solum.circuit.io import CircuitError, circuit_to_dict, load_circuit, save_circuit
from solum.circuit.schema import SCHEMA_VERSION, Circuit, Version, id_from_name

Kind = Literal["circuits", "blocks"]
NOUNS: dict[Kind, str] = {"circuits": "circuit", "blocks": "block"}


def index_table(kind: Kind) -> str:
    return (
        f"CREATE TABLE IF NOT EXISTS {kind} (id TEXT PRIMARY KEY, name TEXT NOT NULL, "
        "tags TEXT NOT NULL, models TEXT NOT NULL, version TEXT NOT NULL, final INTEGER NOT NULL, "
        "problem TEXT, mtime_ns INTEGER NOT NULL, size INTEGER NOT NULL)"
    )


# the columns above: an index from an older app without them is dropped and rebuilt
INDEX_COLUMNS = ("id", "name", "tags", "models", "version", "final", "problem", "mtime_ns", "size")


class StoreError(ValueError):
    """A request about stored circuits that can't be met (plain-English message)."""


_VERSIONED = re.compile(r"^(.+)-v(\d+)$")


def file_id(family: str, major: int) -> str:
    """A version's id (file name): `test-block` at major 2 → `test-block-v2`."""
    return f"{family}-v{major}"


def split_id(circuit_id: str) -> tuple[str, int | None]:
    """(family, major) from a version's id; (id, None) for an id without a version."""
    m = _VERSIONED.match(circuit_id)
    return (m[1], int(m[2])) if m else (circuit_id, None)


def resolve_id(ids: Iterable[str], wanted: str) -> str | None:
    """The id `wanted` names among `ids`: itself, or for a short id (a family) its
    newest major. None when there's neither."""
    known = set(ids)
    if wanted in known:
        return wanted
    majors = [(major, i) for i in known for family, major in [split_id(i)]
              if family == wanted and major is not None]  # fmt: skip
    return max(majors)[1] if majors else None


def current_ids(ids: Iterable[str]) -> set[str]:
    """The current version of each family (its newest major); an id without a version
    is its own current one."""
    newest: dict[str, tuple[int, str]] = {}
    for i in ids:
        family, major = split_id(i)
        key = family if major is not None else i
        if major is None or key not in newest or major > newest[key][0]:
            newest[key] = (major or 0, i)
    return {i for _, i in newest.values()}


def link_id(circuit_id: str, ids: Iterable[str]) -> str:
    """How to link to a version: the short id for the current one, else its own id."""
    return split_id(circuit_id)[0] if circuit_id in current_ids(ids) else circuit_id


def strip_version(name: str, major: int) -> str:
    """A name without a trailing ` v<major>` (what final copies were called, D-075)."""
    m = re.match(rf"^(.*\S)\s+v{major}$", name.strip(), re.IGNORECASE)
    return m[1] if m else name.strip()


@dataclass(frozen=True)
class CircuitEntry:
    """One row of the circuit list. `problem` is set when the file can't be opened;
    `saved` is when its file last changed (ISO 8601, UTC, to the millisecond)."""

    id: str
    name: str
    tags: list[str] = field(default_factory=list)
    models: list[str] = field(default_factory=list)
    version: str = "v1.0"
    final: bool = False
    problem: str | None = None
    current: bool = True
    saved: str = ""


BLANK_RAILS = {"V+": 9.0}


BLANK_PARTS = (
    {"ref": "IN", "type": "guitar", "volume": "250k", "pos": [-300, 0]},
    {"ref": "OUT", "type": "amp", "value": "1M", "pos": [300, 0]},
)


def blank_circuit(name: str) -> Circuit:
    """A new sheet: a guitar input and an amp output, nothing between them, and a 9 V
    rail (the editor's start page; saved with `CircuitStore.create`)."""
    return Circuit.model_validate(
        {"schema": SCHEMA_VERSION, "id": "new", "name": name, "parts": list(BLANK_PARTS),
         "power": {"rails": BLANK_RAILS}}
    )  # fmt: skip


def part_models(circuit: Circuit) -> list[str]:
    """The device models a circuit uses, sorted, each once."""
    return sorted({m for p in circuit.parts if isinstance(m := getattr(p, "model", None), str)})


def _content(circuit: Circuit) -> dict[str, object]:
    """What a save compares to decide whether the file changed: all but the tag and `final`."""
    data = circuit_to_dict(circuit)
    return {k: v for k, v in data.items() if k not in ("version", "final")}


def _stamp(mtime: float, to: Literal["seconds", "milliseconds"]) -> str:
    """A file time as ISO 8601, UTC."""
    return datetime.fromtimestamp(mtime, UTC).isoformat(timespec=to)


def _well_named(circuit_id: str, name: str, version: str) -> bool:
    """An index row whose file already has the app's name for it (or can't be read)."""
    m = re.match(r"^v(\d+)\.", version)
    if not m:
        return True
    major = int(m[1])
    plain = strip_version(name, major)
    return plain == name and circuit_id == file_id(id_from_name(name), major)


class Listed(Protocol):
    @property
    def id(self) -> str: ...
    @property
    def name(self) -> str: ...


def entry_order(entry: Listed) -> tuple[str, int]:
    """List order: by name, then newest major first."""
    return (entry.name.lower(), -(split_id(entry.id)[1] or 0))


class Searchable(Protocol):
    @property
    def name(self) -> str: ...
    @property
    def tags(self) -> list[str]: ...
    @property
    def models(self) -> list[str]: ...


def matches(entry: Searchable, query: str, *more: str) -> bool:
    """Case-insensitive: the query is in the name, any tag or part model, or `more`."""
    q = query.strip().lower()
    texts = (entry.name, *entry.tags, *entry.models, *more)
    return not q or any(q in text.lower() for text in texts)


class CircuitStore:
    def __init__(self, data_dir: Path, cache_dir: Path, kind: Kind = "circuits") -> None:
        self.kind: Kind = kind
        self.noun = NOUNS[kind]
        self.dir = data_dir / kind
        self.cache_dir = cache_dir
        self._lock = threading.Lock()

    @contextmanager
    def _db(self) -> Iterator[sqlite3.Connection]:
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        db = sqlite3.connect(self.cache_dir / "index.sqlite", timeout=30)
        try:
            columns = [row[1] for row in db.execute(f"PRAGMA table_info({self.kind})")]
            if columns and tuple(columns) != INDEX_COLUMNS:
                db.execute(f"DROP TABLE {self.kind}")  # an older index: rebuilt by sync
            db.execute(index_table(self.kind))
            with db:
                yield db
        finally:
            db.close()

    def path(self, circuit_id: str) -> Path:
        if id_from_name(circuit_id, "") != circuit_id:
            raise StoreError(f"{circuit_id!r} isn't a {self.noun} id.")
        return self.dir / f"{circuit_id}.json"

    def ids(self) -> list[str]:
        """Every file's id, sorted."""
        return sorted(p.stem for p in self.dir.glob("*.json")) if self.dir.is_dir() else []

    def resolve(self, circuit_id: str) -> str | None:
        """The file `circuit_id` names: itself, or for a short id the newest major."""
        if id_from_name(circuit_id, "") != circuit_id:
            return None
        return resolve_id(self.ids(), circuit_id)

    def has(self, circuit_id: str) -> bool:
        return self.resolve(circuit_id) is not None

    def link(self, circuit_id: str) -> str:
        """The id to link to: the short one for a current version (D-076)."""
        return link_id(circuit_id, self.ids())

    def versions(self, circuit_id: str) -> list[str]:
        """Every version's id of the circuit `circuit_id` is a version of, oldest first."""
        family = split_id(circuit_id)[0]
        found = [(major, i) for i in self.ids() for f, major in [split_id(i)]
                 if f == family and major is not None]  # fmt: skip
        return [i for _, i in sorted(found)] or [circuit_id]

    def _tidy(self, path: Path) -> Path:
        """Give a file the app's name, `<name>-v<major>.json`, written over with its id;
        a final copy named "<name> v<major>" (D-075) loses the suffix (D-076). A file
        that can't be read, or whose new name is taken, stays as it is."""
        try:
            c = load_circuit(path)
        except CircuitError:
            return path
        name = strip_version(c.name, c.version.major)
        want = file_id(id_from_name(name), c.version.major)
        if want == c.id == path.stem and name == c.name:
            return path
        target = self.dir / f"{want}.json"
        if target != path and target.exists():
            return path
        save_circuit(c.model_copy(update={"id": want, "name": name}), target)
        if target != path:
            path.unlink()
        return target

    def sync(self) -> None:
        """Bring the index up to date with the files: re-read changed or new files (named
        the app's way first, as are misnamed ones), drop rows whose file is gone.
        Unchanged, well-named files aren't opened."""
        with self._lock, self._db() as db:
            rows = db.execute(f"SELECT id, mtime_ns, size, name, version FROM {self.kind}")
            indexed = {r[0]: ((r[1], r[2]), _well_named(r[0], r[3], r[4])) for r in rows}
        known = {cid: stat for cid, (stat, good) in indexed.items() if good}
        paths = sorted(self.dir.glob("*.json")) if self.dir.is_dir() else []
        files: dict[str, Path] = {}
        for path in paths:
            stat = path.stat()
            if known.get(path.stem) != (stat.st_mtime_ns, stat.st_size):
                path = self._tidy(path)
            files[path.stem] = path
        with self._lock, self._db() as db:
            for gone in indexed.keys() - files.keys():
                db.execute(f"DELETE FROM {self.kind} WHERE id = ?", (gone,))
            for cid, path in files.items():
                stat = path.stat()
                if known.get(cid) != (stat.st_mtime_ns, stat.st_size):
                    self._index(db, cid, path, stat.st_mtime_ns, stat.st_size)

    def _index(
        self, db: sqlite3.Connection, cid: str, path: Path, mtime_ns: int, size: int
    ) -> None:
        row: tuple[str, str, str, str, int, str | None]
        try:
            c = load_circuit(path)
            row = (c.name, json.dumps(c.tags), json.dumps(part_models(c)), str(c.version),
                   int(c.final), None)  # fmt: skip
        except CircuitError as err:
            row = (cid, "[]", "[]", "", 0, str(err))
        db.execute(
            f"INSERT OR REPLACE INTO {self.kind} VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (cid, *row, mtime_ns, size),
        )

    def entries(self, query: str = "") -> list[CircuitEntry]:
        """Every stored circuit (or block) matching `query` (all when empty), by name."""
        self.sync()
        with self._lock, self._db() as db:
            rows = db.execute(
                f"SELECT id, name, tags, models, version, final, problem, mtime_ns FROM {self.kind}"
            ).fetchall()
        current = current_ids(r[0] for r in rows)
        found = [
            CircuitEntry(r[0], r[1], json.loads(r[2]), json.loads(r[3]), r[4], bool(r[5]), r[6])
            for r in rows
        ]
        found = [
            replace(e, current=e.id in current, saved=_stamp(r[7] / 1e9, "milliseconds"))
            for e, r in zip(found, rows, strict=True)
        ]
        return sorted((e for e in found if matches(e, query)), key=entry_order)

    def load(self, circuit_id: str) -> Circuit:
        """A saved circuit by id; a short id gives its current version."""
        self.path(circuit_id)  # refuses what isn't an id
        found = self.resolve(circuit_id)
        if found is None:
            raise StoreError(f"There's no saved {self.noun} called {circuit_id!r}.")
        return load_circuit(self.path(found))

    def _write(self, circuit: Circuit) -> Circuit:
        """Write the circuit's own file (its id) and update the index."""
        path = self.path(circuit.id)
        save_circuit(circuit, path)
        stat = path.stat()
        with self._lock, self._db() as db:
            self._index(db, circuit.id, path, stat.st_mtime_ns, stat.st_size)
        return circuit

    def _refuse_final(self, circuit: Circuit) -> None:
        if circuit.final:
            raise StoreError(
                f"{circuit.name} is a final version, so it's read-only. Unlock it in "
                "File \u2192 Properties to change it."
            )

    def save(self, circuit: Circuit) -> Circuit:
        """Write over a saved circuit (its id) and return it as saved: one more on the
        minor version when anything changed, the file untouched when nothing did. A new
        name renames the file (refused if taken). A final version is refused (unlock it
        first). Dismissed problems naming a part or net that's gone are dropped (D-176)."""
        old = self.load(circuit.id)
        self._refuse_final(old)
        circuit = kept_dismissals(circuit)
        if _content(circuit) == _content(old):
            return old
        name = circuit.name.strip()
        new_id = self._rename(old, name) if name != old.name else old.id
        bumped = Version(major=old.version.major, minor=old.version.minor + 1)
        return self._write(
            circuit.model_copy(
                update={"id": new_id, "name": name, "version": bumped, "final": False}
            )
        )

    def _rename(self, old: Circuit, name: str) -> str:
        """Rename every version of `old` to `name` (files and names; their tags stay),
        and return `old`'s new id. Refused when another circuit has the name."""
        family = self._check_free(name, keep=split_id(old.id)[0])
        new_id = old.id
        for vid in self.versions(old.id):
            c = self.load(vid)
            nid = file_id(family, c.version.major)
            self._write(c.model_copy(update={"id": nid, "name": name}))
            if nid != vid:
                self.delete(vid)
            if vid == old.id:
                new_id = nid
        return new_id

    def modified(self, circuit_id: str) -> str:
        """When the file was last saved (ISO 8601, UTC, to the second)."""
        return _stamp(self.path(circuit_id).stat().st_mtime, "seconds")

    def _check_free(self, name: str, keep: str = "") -> str:
        """The short id (file names without the version) for `name`; refused when another
        circuit (any version) has it, or the name ends in a version like `v2`."""
        name = name.strip()
        if not name:
            raise StoreError(f"Give the {self.noun} a name.")
        family = id_from_name(name)
        if split_id(family)[1] is not None:
            raise StoreError(
                f"Leave the version out of the name ({name}): Solum Builder keeps it for you "
                "(v1.0, v2.0, …)."
            )
        taken = family != keep and resolve_id(self.ids(), family)
        if taken:
            raise StoreError(
                f"You already have a {self.noun} called {self.load_name(taken)} (its file is "
                f"{taken}.json). Pick another name."
            )
        return family

    def load_name(self, circuit_id: str) -> str:
        try:
            return self.load(circuit_id).name
        except CircuitError:
            return circuit_id

    def update_info(
        self,
        circuit_id: str,
        *,
        name: str | None = None,
        description: str | None = None,
        tags: list[str] | None = None,
        final: bool | None = None,
    ) -> Circuit:
        """Change a saved circuit's name (its file is renamed with it), description,
        tags, or whether it's final. Name, description and tags count as a change (one
        more on the minor); locking or unlocking doesn't. A final version's details
        can't change unless it's unlocked in the same request."""
        old = self.load(circuit_id)
        info: dict[str, object] = {"description": description, "tags": tags}
        if name is not None:
            info["name"] = name.strip()
        changed = {k: v for k, v in info.items() if v is not None and v != getattr(old, k)}
        if changed and final is not False:
            self._refuse_final(old)
        new_id = old.id
        if isinstance(changed.get("name"), str):
            new_id = self._rename(old, str(changed["name"]))  # every version
        update: dict[str, object] = {**changed, "id": new_id}
        if final is not None:
            update["final"] = final
        if changed:
            update["version"] = Version(major=old.version.major, minor=old.version.minor + 1)
        return self._write(self.load(new_id).model_copy(update=update))

    def new_major(self, circuit_id: str) -> tuple[Circuit, Circuit]:
        """Mark the current version final (read-only; its tag stays) and carry on in a
        new file at the next major (`<name>-v2.json`, v2.0). Returns (current, final)."""
        old = self.load(circuit_id)
        family, _ = split_id(old.id)
        if old.id != resolve_id(self.ids(), family):
            raise StoreError(
                f"There's a newer version of {old.name}: start the next major version from "
                "the newest one."
            )
        final = self._write(old.model_copy(update={"final": True})) if not old.final else old
        major = old.version.major + 1
        current = self._write(
            old.model_copy(
                update={
                    "id": file_id(family, major),
                    "version": Version(major=major),
                    "final": False,
                }
            )
        )
        return current, final

    def delete(self, circuit_id: str) -> None:
        """Remove one version's file and its index row (a short id: the current one)."""
        self.path(circuit_id)  # refuses what isn't an id
        circuit_id = self.resolve(circuit_id) or circuit_id
        path = self.path(circuit_id)
        if not path.is_file():
            raise StoreError(f"There's no saved {self.noun} called {circuit_id!r}.")
        path.unlink()
        with self._lock, self._db() as db:
            db.execute(f"DELETE FROM {self.kind} WHERE id = ?", (circuit_id,))

    def create(self, circuit: Circuit, name: str | None = None) -> Circuit:
        """Save as a new circuit (`<name>-v1`; never a starter, at v1.0, not final) and
        return it. A name another circuit has is refused. Dismissed problems naming a part
        or net that's gone are dropped (D-176)."""
        name = (name if name is not None else circuit.name).strip()
        new_id = file_id(self._check_free(name), 1)
        new = kept_dismissals(circuit).model_copy(
            update={
                "id": new_id,
                "name": name,
                "starter": False,
                "version": Version(),
                "final": False,
            }
        )
        return self._write(new)
