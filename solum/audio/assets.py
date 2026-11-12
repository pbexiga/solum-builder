"""Clips, amp captures and cab IRs: built-in ones in `library/audio/<kind>/` (read-only,
each with its source and licence in `library/audio/sources.yaml`) and the user's uploads
in `DATA_DIR/audio/<kind>/` (D-083).

Files are the source of truth; there is no index (a handful of files, read on listing).
An upload is checked before it's kept: a clip must be a readable WAV of at most 10 s, a
capture a supported `.nam`, an IR a short WAV.
"""

from dataclasses import dataclass
from pathlib import Path
from typing import Literal

from solum.audio.ir import load_ir
from solum.audio.nam import NamError, load_nam
from solum.audio.render import RATE, read_clip
from solum.audio.wav import WavError
from solum.circuit.schema import id_from_name

Kind = Literal["clips", "captures", "irs"]
KINDS: tuple[Kind, ...] = ("clips", "captures", "irs")
SUFFIX: dict[Kind, str] = {"clips": ".wav", "captures": ".nam", "irs": ".wav"}
AssetLayer = Literal["user", "core"]
LAYERS: tuple[AssetLayer, ...] = ("user", "core")
MAX_UPLOAD_BYTES = 50_000_000  # a 10 s 192 kHz 32-bit stereo WAV is ~15 MB


class AssetError(ValueError):
    """An asset can't be found, read or kept (plain-English message)."""


@dataclass(frozen=True)
class AssetEntry:
    id: str
    name: str  # the file name it was uploaded as, without its extension
    kind: Kind
    layer: AssetLayer
    detail: str  # "4.8 s", a capture's own name, "200 ms"


def describe(kind: Kind, data: bytes) -> str:
    """A short description, after checking the file is usable (AssetError if not)."""
    try:
        if kind == "clips":
            clip = read_clip(data)
            return f"{clip.seconds:.1f} s · {_khz(clip.rate)}"
        if kind == "captures":
            nam = load_nam(data)  # its own rate, said so (most are 48 kHz, D-105)
            return " · ".join(filter(None, [nam.name, _khz(nam.sample_rate)]))
        return f"{len(load_ir(data, RATE)) / RATE * 1000:.0f} ms"
    except (WavError, NamError) as err:
        raise AssetError(str(err)) from None


class AudioLibrary:
    def __init__(self, core_dir: Path, data_dir: Path) -> None:
        self.dirs: dict[AssetLayer, Path] = {"user": data_dir / "audio", "core": core_dir}

    def _files(self, kind: Kind, layer: AssetLayer) -> list[Path]:
        folder = self.dirs[layer] / kind
        return sorted(folder.glob(f"*{SUFFIX[kind]}")) if folder.is_dir() else []

    def entries(self, kind: Kind) -> list[AssetEntry]:
        """The user's first, then the built-in ones, each by name. Files that can't be
        read are left out (an upload is checked, so only a hand-copied file can be)."""
        found = []
        for layer in LAYERS:
            for path in self._files(kind, layer):
                try:
                    detail = describe(kind, path.read_bytes())
                except (AssetError, OSError):
                    continue
                found.append(AssetEntry(path.stem, path.stem, kind, layer, detail))
        return found

    def path(self, kind: Kind, asset_id: str, layer: AssetLayer) -> Path:
        path = self.dirs[layer] / kind / f"{asset_id}{SUFFIX[kind]}"
        if id_from_name(asset_id, "") != asset_id or not path.is_file():
            raise AssetError(f"There's no {_noun(kind)} called {asset_id!r}.")
        return path

    def read(self, kind: Kind, asset_id: str, layer: AssetLayer) -> bytes:
        return self.path(kind, asset_id, layer).read_bytes()

    def add(self, kind: Kind, filename: str, data: bytes) -> AssetEntry:
        """Keep an upload in the user's folder, named after its file (`-2`, `-3`… when the
        name is taken). AssetError if it isn't usable."""
        if len(data) > MAX_UPLOAD_BYTES:
            raise AssetError(f"This file is too big ({len(data) / 1e6:.0f} MB).")
        detail = describe(kind, data)
        stem = id_from_name(Path(filename).stem, _noun(kind).replace(" ", "-"))
        folder = self.dirs["user"] / kind
        folder.mkdir(parents=True, exist_ok=True)
        asset_id, n = stem, 2
        while (folder / f"{asset_id}{SUFFIX[kind]}").exists():
            asset_id, n = f"{stem}-{n}", n + 1
        path = folder / f"{asset_id}{SUFFIX[kind]}"
        tmp = path.with_suffix(".tmp")
        tmp.write_bytes(data)
        tmp.replace(path)
        return AssetEntry(asset_id, asset_id, kind, "user", detail)

    def delete(self, kind: Kind, asset_id: str) -> None:
        """Delete one of the user's uploads (built-in ones can't be)."""
        self.path(kind, asset_id, "user").unlink()


def _khz(rate: float) -> str:
    """A sample rate as a file's description gives it: "48 kHz", "44.1 kHz"."""
    return f"{rate / 1000:g} kHz"


def _noun(kind: Kind) -> str:
    return {"clips": "clip", "captures": "amp capture", "irs": "cab IR"}[kind]
