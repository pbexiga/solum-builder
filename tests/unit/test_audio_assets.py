from pathlib import Path

import numpy as np
import pytest

from solum.audio.assets import AssetError, AudioLibrary
from solum.audio.wav import Audio, write_wav

NAM = Path(__file__).resolve().parents[1] / "fixtures" / "nam" / "standard-random.nam"


def wav(seconds: float, rate: int = 8000) -> bytes:
    return write_wav(Audio(rate, np.sin(np.arange(int(rate * seconds)) / 3)))


@pytest.fixture
def lib(tmp_path: Path) -> AudioLibrary:
    core = tmp_path / "core"
    (core / "clips").mkdir(parents=True)
    (core / "clips" / "lead.wav").write_bytes(wav(2.0))
    (core / "clips" / "broken.wav").write_bytes(b"nope")  # left out of the list
    return AudioLibrary(core, tmp_path / "data")


def test_uploads_are_listed_before_built_ins(lib: AudioLibrary) -> None:
    added = lib.add("clips", "My Riff (take 2).WAV", wav(1.5))
    assert (added.id, added.layer, added.detail) == ("my-riff-take-2", "user", "1.5 s · 8 kHz")
    assert [(e.id, e.layer) for e in lib.entries("clips")] == [
        ("my-riff-take-2", "user"), ("lead", "core"),
    ]  # fmt: skip
    assert lib.read("clips", "lead", "core") == wav(2.0)


def test_a_taken_name_gets_a_number(lib: AudioLibrary) -> None:
    assert lib.add("clips", "riff.wav", wav(1)).id == "riff"
    assert lib.add("clips", "riff.wav", wav(1)).id == "riff-2"
    assert lib.add("clips", "riff.wav", wav(1)).id == "riff-3"


def test_each_kind_is_checked_before_it_is_kept(lib: AudioLibrary, tmp_path: Path) -> None:
    with pytest.raises(AssetError, match="up to 10 s"):
        lib.add("clips", "long.wav", wav(11))
    with pytest.raises(AssetError, match="isn't a NAM capture"):
        lib.add("captures", "amp.nam", wav(1))
    with pytest.raises(AssetError, match="cab IR"):
        lib.add("irs", "room.wav", wav(3))
    assert not list((tmp_path / "data").rglob("*.*"))
    plexi = lib.add("captures", "Plexi.nam", NAM.read_bytes())
    assert plexi.id == "plexi" and plexi.detail.endswith(" kHz")  # its own rate, said (D-105)
    assert lib.add("irs", "4x12.wav", wav(0.1)).detail == "100 ms"


def test_only_uploads_can_be_deleted(lib: AudioLibrary) -> None:
    lib.add("clips", "riff.wav", wav(1))
    lib.delete("clips", "riff")
    assert [e.id for e in lib.entries("clips")] == ["lead"]
    with pytest.raises(AssetError, match="no clip called 'lead'"):
        lib.delete("clips", "lead")


@pytest.mark.parametrize("bad", ["../core/clips/lead", "", "Lead", "a/b"])
def test_ids_never_reach_outside_their_folder(lib: AudioLibrary, bad: str) -> None:
    with pytest.raises(AssetError):
        lib.read("clips", bad, "user")
