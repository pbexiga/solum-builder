import pytest

from solum import cli


def test_bad_setting_prints_plain_message(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setenv("PORT", "eighty")
    assert cli.main(["bench"]) == 1
    assert capsys.readouterr().err.startswith("solum: PORT must be a whole number")


def test_command_is_required() -> None:
    with pytest.raises(SystemExit):
        cli.main([])
