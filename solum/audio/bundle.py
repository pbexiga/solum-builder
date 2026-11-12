"""All of a session's takes in one zip, with what each was made from (D-096)."""

import io
import zipfile


def safe_file_name(text: str, fallback: str = "render") -> str:
    """`text` as a file name: letters, digits, `-`, `_`, `.`, `%` and spaces kept, anything
    else (slashes, quotes) turned to `-`."""
    safe = "".join(ch if ch.isalnum() or ch in "-_ .%" else "-" for ch in text).strip(" .")
    return safe or fallback


def zip_takes(takes: list[tuple[str, bytes]], files: dict[str, str]) -> bytes:
    """A zip of `takes` (file name, WAV bytes) and the text `files`, each name made safe.
    WAVs are stored as they are (they hardly compress); text is deflated."""
    out = io.BytesIO()
    with zipfile.ZipFile(out, "w") as z:
        for name, data in takes:
            z.writestr(safe_file_name(name), data, compress_type=zipfile.ZIP_STORED)
        for name, text in files.items():
            z.writestr(safe_file_name(name), text, compress_type=zipfile.ZIP_DEFLATED)
    return out.getvalue()
