"""WAV files in and out (the one owner). Standard library and numpy only.

Reads PCM (8, 16, 24, 32-bit) and float (32, 64-bit), plain or WAVE_FORMAT_EXTENSIBLE,
any number of channels (mixed to mono). Writes mono 32-bit float, which every browser
plays and keeps levels above full scale intact.
"""

import struct
from dataclasses import dataclass

import numpy as np
import numpy.typing as npt

Array = npt.NDArray[np.float64]

_PCM, _FLOAT, _EXTENSIBLE = 1, 3, 0xFFFE


class WavError(ValueError):
    """The file isn't a WAV file Solum Builder can read (plain-English message)."""


@dataclass(frozen=True)
class Audio:
    rate: int  # samples per second
    samples: Array  # mono, full scale = ±1

    @property
    def seconds(self) -> float:
        return len(self.samples) / self.rate


def _chunks(data: bytes) -> dict[bytes, bytes]:
    if len(data) < 12 or data[:4] != b"RIFF" or data[8:12] != b"WAVE":
        raise WavError("This isn't a WAV file. Export the clip as WAV and upload that.")
    found: dict[bytes, bytes] = {}
    i = 12
    while i + 8 <= len(data):
        cid, size = data[i : i + 4], struct.unpack("<I", data[i + 4 : i + 8])[0]
        found.setdefault(cid, data[i + 8 : i + 8 + size])
        i += 8 + size + (size & 1)  # chunks are padded to even sizes
    return found


def read_wav(data: bytes) -> Audio:
    """A WAV file's audio as mono floats. WavError if it can't be read."""
    chunks = _chunks(data)
    fmt, raw = chunks.get(b"fmt "), chunks.get(b"data")
    if fmt is None or raw is None or len(fmt) < 16:
        raise WavError("This WAV file is missing its format or audio data.")
    code, channels, rate, _, align, bits = struct.unpack("<HHIIHH", fmt[:16])
    if code == _EXTENSIBLE and len(fmt) >= 26:
        code = struct.unpack("<H", fmt[24:26])[0]  # the sub-format GUID starts with it
    if channels < 1 or rate < 1 or align < 1:
        raise WavError("This WAV file's header is damaged.")
    width = align // channels
    frames = len(raw) // align
    raw = raw[: frames * align]
    if code == _FLOAT and width in (4, 8):
        x = np.frombuffer(raw, dtype=f"<f{width}").astype(np.float64)
    elif code == _PCM and width == 1:
        x = (np.frombuffer(raw, dtype=np.uint8).astype(np.float64) - 128) / 128
    elif code == _PCM and width in (2, 4):
        x = np.frombuffer(raw, dtype=f"<i{width}").astype(np.float64) / 2.0 ** (8 * width - 1)
    elif code == _PCM and width == 3:
        b = np.frombuffer(raw, dtype=np.uint8).reshape(-1, 3).astype(np.int32)
        v = b[:, 0] | (b[:, 1] << 8) | (b[:, 2] << 16)
        x = np.where(v >= 1 << 23, v - (1 << 24), v).astype(np.float64) / 2.0**23
    else:
        raise WavError(
            f"This WAV file uses an encoding Solum Builder can't read "
            f"({bits}-bit, format {code}). Export it as 16-bit, 24-bit or 32-bit float WAV."
        )
    return Audio(rate, x.reshape(frames, channels).mean(axis=1))


def write_wav(audio: Audio) -> bytes:
    """Mono 32-bit float WAV bytes."""
    data = np.asarray(audio.samples, dtype="<f4").tobytes()
    fmt = struct.pack("<HHIIHH", _FLOAT, 1, audio.rate, audio.rate * 4, 4, 32)
    body = b"WAVE" + b"fmt " + struct.pack("<I", len(fmt)) + fmt
    body += b"data" + struct.pack("<I", len(data)) + data
    return b"RIFF" + struct.pack("<I", len(body)) + body
