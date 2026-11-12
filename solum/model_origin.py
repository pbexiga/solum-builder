"""Whose card a model is (D-156, D-186): ours fitted from a sheet, ours estimated with no
sheet, a maker's card pulled from a SPICE library, the maker's own, or one the user
added from their own file. The one owner for the app's parts list
(`Model.catalogue_entry`) and the models index (`scripts/models_index.py`). It reads a
record as JSON (a dict) and imports nothing outside the standard library, so the index
script runs without the app's dependencies.
"""

from collections.abc import Mapping
from typing import Any, Literal

FIT = "Solum Builder fit"  # a record's source.original for our own fit (D-156)
ESTIMATE = "Solum Builder estimate"  # ... for a card estimated with no sheet to fit (D-186)
USER = "Added by you"  # ... for a card the user added from their own file (9c)
LIBRARY = "kicad-spice-library"  # in a source URL: a card pulled from that collection

Origin = Literal["ours", "estimate", "library", "maker", "user"]


def card_origin(record: Mapping[str, Any]) -> tuple[Origin, str]:
    """Whose card it is, and its detail: the sheet it was fitted to (or estimated from),
    the library file it was pulled from, the maker's name, or the file the user added it
    from."""
    source = record["source"]
    original = source.get("original", "")
    if original == FIT:
        return "ours", record["fit"]["sheet"]
    if original == ESTIMATE:
        return "estimate", record["fit"]["sheet"]
    if original == USER:
        return "user", source["url"]
    if LIBRARY in source["url"]:
        return "library", source["url"].rsplit("/", 1)[-1].replace("%20", " ")
    return "maker", original or record.get("manufacturer") or source["url"]
