"""Write the Shipped table of data/spec-sheets/README.md from the model records (D-156).

`python3 scripts/models_index.py` rewrites the table between its markers; a unit test
fails when the committed table no longer matches `library/models/`. The Licence column
is the review of each source file the models came from: who owns the file, and whether
shipping it is settled or waits for the user's decision.
"""

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from solum.model_origin import card_origin  # noqa: E402  (stdlib only)

MODELS = ROOT / "library" / "models"
INDEX = ROOT / "data" / "spec-sheets" / "README.md"
START, END = "<!-- shipped:start -->", "<!-- shipped:end -->"

LTSPICE = "LTspice's library (Analog Devices, all rights reserved)"
# The file a model came from (the end of its source URL) → what was found in it.
FILES = {
    "BJT.lib": LTSPICE,
    "DIODE2.lib": LTSPICE,
    "JFET2.lib": LTSPICE,
    "standard.dio": LTSPICE,
    "JFET.LIB": "Intusoft's library (all rights reserved)",
    "phil_fet.lib": "Philips' own library, no notice",
    "zener.lib": "Diodes Incorporated's models, no notice",
}
SETTLED = "Settled"
DECIDE_MAKER = "Decide: the maker's model inside {file}"
OFF_LIMITS = "Decide: names no maker, so it's the file owner's ({file}); off limits under D-152"


def licence_status(record: dict) -> str:
    """Settled, or what the user has to decide, for one model record."""
    source = record["source"]
    url, licence = source["url"], source.get("licence", "")
    original = source.get("original", "")
    file = url.rsplit("/", 1)[-1].replace("%20", " ")
    if "kicad-spice-library" in url:
        found = FILES.get(file)
        if found is None:  # the TI op-amp macromodels: TI's own files, no notice
            return (
                f"{SETTLED}: {original}' own model, no notice"
                if original.endswith("s")
                else f"{SETTLED}: {original}'s own model, no notice"
            )
        if found.startswith("Intusoft"):
            return f"Decide: {found}; off limits under D-151"
        if found == LTSPICE:
            named = original and not original.startswith("unattributed")
            return (DECIDE_MAKER if named else OFF_LIMITS).format(file=found)
        return f"{SETTLED}: {found}"
    if "CC BY-NC" in licence:
        return "Decide: CC BY-NC (non-commercial only)"
    if "to settle" in licence:
        return "Decide: the maker's terms don't say whether it may be passed on"
    return f"{SETTLED}: {licence}"


def card(record: dict) -> str:
    """Whose card it is, in words (`solum.model_origin`, shared with the app's parts list)."""
    kind, detail = card_origin(record)
    return {
        "ours": f"Ours (fitted from {detail})",
        "estimate": f"Estimated ({detail})",
        "library": f"Pulled (KiCad-Spice-Library, {detail})",
        "maker": f"Pulled ({detail})",
        "user": f"Added by the user ({detail})",
    }[kind]


def checks(record: dict) -> str:
    """How many datasheet checks the record holds, and the documents they cite."""
    cited = [v for v in record.get("validation", []) if v.get("datasheet")]
    docs = sorted({v["datasheet"]["source"].split(",")[0] for v in cited})
    return f"{len(cited)}: {'; '.join(docs)}" if cited else "none"


def shipped_table(models: Path = MODELS) -> str:
    rows = ["| Part | Type | Model by | Card | Source | Datasheet checks | Licence |",
            "|---|---|---|---|---|---|---|"]  # fmt: skip
    records = [json.loads(p.read_text(encoding="utf-8")) for p in models.glob("*/*.json")]
    for r in sorted(records, key=lambda r: (r["type"], r["id"])):
        source = r["source"]
        rows.append(
            f"| {r['id']} | {r['type']} | "
            f"{source.get('original') or r.get('manufacturer') or 'no maker named'} "
            f"| {card(r)} | {source['url']} | {checks(r)} | {licence_status(r)} |"
        )
    return "\n".join(rows)


def with_table(index: str, table: str) -> str:
    head, rest = index.split(START, 1)
    _, tail = rest.split(END, 1)
    return f"{head}{START}\n{table}\n{END}{tail}"


def main() -> int:
    index = INDEX.read_text(encoding="utf-8")
    INDEX.write_text(with_table(index, shipped_table()), encoding="utf-8")
    return 0


if __name__ == "__main__":
    sys.exit(main())
