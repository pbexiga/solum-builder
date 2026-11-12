"""Clean-up review helper: same-named functions in several files, and repeated runs of lines."""

import collections
import pathlib
import re
import sys

roots = sys.argv[1:] or ["solum", "web"]
files = [
    p
    for r in roots
    for p in pathlib.Path(r).rglob("*")
    if p.suffix in (".py", ".js") and "vendor" not in p.parts
]
names = collections.defaultdict(list)
for p in files:
    for i, line in enumerate(p.read_text().splitlines(), 1):
        m = re.match(r"\s*(?:export\s+)?(?:async\s+)?(?:def|function)\s+(\w+)", line) or re.match(
            r"(?:export\s+)?const\s+(\w+)\s*=\s*(?:async\s*)?\(", line
        )
        if m:
            names[m.group(1)].append(f"{p}:{i}")
print("== same name, several files")
for n, where in sorted(names.items()):
    if (
        len({w.split(":")[0] for w in where}) > 1
        and not n.startswith("__")
        and n
        not in (
            "go",
            "run",
            "body",
            "read",
            "close",
            "show",
            "update",
            "render",
            "draw",
            "clear",
            "refresh",
            "open",
            "key",
            "main",
        )
    ):
        print(f"{n}: {' '.join(where)}")
N = 5
print(f"== runs of {N}+ same lines")
seen = collections.defaultdict(list)
for p in files:
    lines = [re.sub(r"\s+", " ", row.strip()) for row in p.read_text().splitlines()]
    idx = [
        (i, row)
        for i, row in enumerate(lines, 1)
        if len(row) > 12 and not row.startswith(("#", "//", "*", "/*", '"""', "import ", "from "))
    ]
    for k in range(len(idx) - N + 1):
        win = idx[k : k + N]
        seen["\n".join(row for _, row in win)].append((str(p), win[0][0]))
out = {}
for text, where in seen.items():
    if len(where) > 1:
        key = tuple(sorted({(f, ln) for f, ln in where}))
        out[key] = text
last = None
for key in sorted(out):
    # skip windows that continue the previous clone
    tag = tuple((f, ln - (last[1] if last else 0)) for f, ln in key)
    if (
        last
        and all(
            f == pf and 0 < ln - pl <= 2 for (f, ln), (pf, pl) in zip(key, last[0], strict=False)
        )
        and len(key) == len(last[0])
    ):
        last = (key, 0)
        continue
    print(" | ".join(f"{f}:{ln}" for f, ln in key))
    print("    " + out[key].split("\n")[0][:110])
    last = (key, 0)
