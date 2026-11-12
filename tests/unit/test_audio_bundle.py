"""All takes in one zip (D-096)."""

import io
import zipfile

from solum.audio.bundle import safe_file_name, zip_takes


def test_file_names_are_made_safe() -> None:
    assert safe_file_name("TS808 Drive 75 %.wav") == "TS808 Drive 75 %.wav"
    assert safe_file_name('a/b\\c:"d"') == "a-b-c--d-"
    assert safe_file_name("../..") == "-"  # no climbing out of the folder
    assert safe_file_name(" . ") == "render"
    assert safe_file_name("µ Fuzz") == "µ Fuzz"  # letters of any script stay


def test_zip_holds_the_takes_as_they_are_and_the_text_files() -> None:
    wav = b"RIFF" + bytes(range(256)) * 4
    notes = "Pedal.wav\n  Knobs: Drive 50 %\n"
    data = zip_takes([("Pedal.wav", wav), ("Drive 0 %.wav", b"RIFF2")],
                     {"takes.txt": notes, "Pedal.json": "{}"})  # fmt: skip
    with zipfile.ZipFile(io.BytesIO(data)) as z:
        assert z.namelist() == ["Pedal.wav", "Drive 0 %.wav", "takes.txt", "Pedal.json"]
        assert z.read("Pedal.wav") == wav
        assert z.getinfo("Pedal.wav").compress_type == zipfile.ZIP_STORED
        assert z.getinfo("takes.txt").compress_type == zipfile.ZIP_DEFLATED
        assert z.read("takes.txt").decode() == "Pedal.wav\n  Knobs: Drive 50 %\n"


def test_an_empty_zip_is_still_a_zip() -> None:
    with zipfile.ZipFile(io.BytesIO(zip_takes([], {}))) as z:
        assert z.namelist() == []
