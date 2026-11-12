# ruff: noqa: E501  (JavaScript inside strings)
"""scripts/jscheck.js, the browser code's static check (D-286): what it reports and what
it lets through, on small modules written to a temp folder."""

import subprocess
from pathlib import Path

import pytest

from tests.conftest import REPO

playwright = pytest.importorskip("playwright")  # the check runs on the node Playwright ships


def findings(tmp_path: Path, files: dict[str, str], check: str = "a.js") -> list[str]:
    for name, text in files.items():
        (tmp_path / name).write_text(text)
    done = subprocess.run(
        [str(REPO / "scripts" / "jscheck.sh"), str(tmp_path / check)],
        capture_output=True, text=True, check=False,
    )  # fmt: skip
    lines = [line.split(": ", 1)[1] for line in done.stdout.splitlines() if ": " in line]
    assert (done.returncode != 0) == bool(lines), done.stderr
    return lines


def test_a_name_never_declared_is_reported_with_its_line(tmp_path: Path) -> None:
    (tmp_path / "a.js").write_text("const a = 1;\nexport const b = a + missing;\n")
    done = subprocess.run([str(REPO / "scripts" / "jscheck.sh"), str(tmp_path / "a.js")],
                          capture_output=True, text=True, check=False)  # fmt: skip
    assert done.returncode == 1
    assert done.stdout.splitlines()[0].endswith(
        "a.js:2: missing is not defined (not declared or imported in this file)"
    )


def test_declarations_of_every_kind_are_known(tmp_path: Path) -> None:
    source = """
import { used } from "./b.js";
export function f(a, { b, c: [d] = [] }, ...rest) {
  const { e, ...others } = a;
  for (const [k, v] of Object.entries(others)) later(k, v, rest);
  try { used(b, d, e); } catch (err) { console.log(err.message); }
  for (let i = 0; i < 3; i++) hoisted(i);
  switch (a) { case 1: { const inner = 2; return inner; } default: return (x) => x + f.length; }
}
function later() {}
var hoisted = (n) => n;
class Thing extends Object { static make() { return new Thing(); } get size() { return this.n; } }
label: for (;;) { break label; }
export const made = { used, key: Thing, [hoisted.name]: document.body, short() { return window.innerWidth; } };
"""
    assert findings(tmp_path, {"a.js": source, "b.js": "export const used = 1;\n"}) == []


def test_a_use_before_the_block_that_declares_it_is_reported(tmp_path: Path) -> None:
    source = "export function f() {\n  { const inner = 1; }\n  return inner;\n}\n"
    assert findings(tmp_path, {"a.js": source}) == [
        "inner is not defined (not declared or imported in this file)"
    ]


def test_property_names_and_object_keys_are_not_uses(tmp_path: Path) -> None:
    source = "const o = { nowhere: 1 };\nexport const v = o.nowhere + o?.other;\n"
    assert findings(tmp_path, {"a.js": source}) == []


def test_an_unused_import_is_reported_even_when_a_key_has_its_name(tmp_path: Path) -> None:
    source = 'import { one, two } from "./b.js";\nexport const o = { two: one };\n'
    b = "export const one = 1;\nexport const two = 2;\n"
    assert findings(tmp_path, {"a.js": source, "b.js": b}) == ["two is imported but never used"]


def test_an_import_shadowed_by_a_parameter_is_still_unused(tmp_path: Path) -> None:
    source = 'import { one } from "./b.js";\nexport const f = (one) => one;\n'
    assert findings(tmp_path, {"a.js": source, "b.js": "export const one = 1;\n"}) == [
        "one is imported but never used"
    ]


def test_importing_what_the_other_module_does_not_export_is_reported(tmp_path: Path) -> None:
    source = 'import { one, gone } from "./b.js";\nexport const v = one + gone;\n'
    b = "const gone = 2;\nexport function one() { return gone; }\n"
    assert findings(tmp_path, {"a.js": source, "b.js": b}) == ["./b.js doesn't export gone"]


def test_a_file_that_does_not_parse_says_so(tmp_path: Path) -> None:
    assert findings(tmp_path, {"a.js": "export const = 1;\n"})[0].startswith("doesn't parse")


def test_the_browser_code_is_clean() -> None:
    done = subprocess.run(
        [str(REPO / "scripts" / "jscheck.sh")], capture_output=True, text=True, check=False
    )
    assert done.returncode == 0, done.stdout
