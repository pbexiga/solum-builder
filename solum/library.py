"""Blocks: reusable circuits the editor pastes into other circuits (D-010, D-072, D-075).

Two layers, both always listed. Core blocks ship in `library/blocks/` and never change
(the app reads them, never writes them); the user's own (My blocks) live in
`DATA_DIR/blocks/`, in the same store as circuits (renaming, version tags, final
versions). Pasting is an edit, so it happens in the editor (`web/editor/blocks.js`) and
copies the block's parts: nothing in a circuit links back to the block.
"""

from dataclasses import dataclass, field
from pathlib import Path
from typing import Literal

from solum.circuit.io import CircuitError, load_circuit
from solum.circuit.schema import Circuit
from solum.store import (
    CircuitStore,
    StoreError,
    current_ids,
    entry_order,
    link_id,
    matches,
    part_models,
    resolve_id,
)

Layer = Literal["user", "core"]
LAYERS: tuple[Layer, ...] = ("user", "core")  # lookup order when no layer is given


@dataclass(frozen=True)
class BlockEntry:
    """One row of the block list."""

    id: str
    name: str
    layer: Layer
    description: str = ""
    tags: list[str] = field(default_factory=list)
    ports: list[str] = field(default_factory=list)
    models: list[str] = field(default_factory=list)
    version: str = "v1.0"
    final: bool = False
    problem: str | None = None
    current: bool = True


class BlockLibrary:
    def __init__(self, core_dir: Path, data_dir: Path, cache_dir: Path) -> None:
        self.core_dir = core_dir
        self.user = CircuitStore(data_dir, cache_dir, kind="blocks")

    def _core_paths(self) -> dict[str, Path]:
        if not self.core_dir.is_dir():
            return {}
        return {p.stem: p for p in sorted(self.core_dir.glob("*.json"))}

    def _entry(self, block_id: str, layer: Layer, path: Path, current: bool) -> BlockEntry:
        try:
            c = load_circuit(path)
        except CircuitError as err:
            return BlockEntry(block_id, block_id, layer, problem=str(err), current=current)
        return BlockEntry(block_id, c.name, layer, c.description, c.tags, list(c.ports),
                          part_models(c), str(c.version), c.final, None, current)  # fmt: skip

    def entries(self, query: str = "") -> list[BlockEntry]:
        """Every block matching `query` (name, tag, part model or description): My
        blocks, then core, each by name, newest major first."""
        mine = self.user.entries()
        found = [self._entry(e.id, "user", self.user.path(e.id), e.current) for e in mine]
        core = self._core_paths()
        now = current_ids(core)
        found += [self._entry(i, "core", p, i in now) for i, p in core.items()]
        found = [e for e in found if matches(e, query, e.description)]
        return sorted(found, key=lambda e: (e.layer != "user", *entry_order(e)))

    def get(self, block_id: str, layer: Layer | None = None) -> tuple[Circuit, Layer]:
        """A block by id (a short id gives its current version): from `layer`, or the
        user's if there is one, else core."""
        for here in (layer,) if layer else LAYERS:
            if here == "user" and self.user.has(block_id):
                return self.user.load(block_id), "user"
            core = self._core_paths()
            if here == "core" and (found := resolve_id(core, block_id)):
                return load_circuit(core[found]), "core"
        raise StoreError(f"There's no block called {block_id!r}.")

    def link(self, block_id: str, layer: Layer) -> str:
        """The id to link to: the short one for a current version (D-076)."""
        if layer == "user":
            return self.user.link(block_id)
        return link_id(block_id, self._core_paths())

    def create(self, circuit: Circuit, name: str) -> Circuit:
        """Save as a new block in My blocks (v1.0). A name already in My blocks is refused."""
        block = circuit.model_copy(update={"template": True, "starter": False})
        return self.user.create(block, name)

    def save(self, circuit: Circuit) -> Circuit:
        """Write over one of My blocks (one more on its minor version when it changed)."""
        if not self.user.has(circuit.id):
            raise StoreError(f"There's no block called {circuit.id!r} in My blocks.")
        return self.user.save(circuit.model_copy(update={"template": True, "starter": False}))

    def delete(self, block_id: str) -> None:
        """Delete one version of one of My blocks (a short id: the current one). Core
        blocks can't be deleted."""
        found = self.user.resolve(block_id)
        if found is None:
            if resolve_id(self._core_paths(), block_id):
                raise StoreError("Core blocks can't be deleted.")
            raise StoreError(f"There's no block called {block_id!r} in My blocks.")
        self.user.delete(found)
