"""Cards the app may not ship (D-156's *Decide* cards, National's LM13700, D-183), listed in
Tools → Parts and datasheets as *not included* with where to get each (9c). Nothing is
fetched: the user adds a card with Tools → Add a model, and once it's in the library the
entry is no longer listed. The list is `library/models/not-included.json`."""

from pathlib import Path
from typing import Any

from pydantic import BaseModel, ConfigDict, ValidationError, model_validator

from solum.models import Model, ModelError, ModelLibrary, ModelType

FILE = "not-included.json"  # in the core models folder, beside the `<type>/` folders


class _Strict(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class Reason(_Strict):
    why: str  # whose terms keep it out, in plain words
    get: str  # what to download, with `{file}` for the card's file name


class Card(_Strict):
    id: str  # the part, as the parts list shows it
    type: ModelType
    card: str  # its `.model` or `.subckt` name in the file
    description: str
    maker: str  # "" when the card names none
    source: str  # a key of `NotIncluded.sources`
    file: str  # the file to get ("" when the card is printed on a page)
    url: str


class NotIncluded(_Strict):
    sources: dict[str, Reason]
    cards: list[Card]

    @model_validator(mode="after")
    def _known_sources(self) -> "NotIncluded":
        if missing := {c.source for c in self.cards} - set(self.sources):
            raise ValueError(f"cards name sources not listed: {sorted(missing)}")
        return self


def load_not_included(models_dir: Path) -> NotIncluded:
    """The list in `models_dir` (the core `library/models`); empty when it has none."""
    path = models_dir / FILE
    if not path.is_file():
        return NotIncluded(sources={}, cards=[])
    try:
        return NotIncluded.model_validate_json(path.read_text(encoding="utf-8"))
    except ValidationError as err:
        raise ModelError(f"The list of cards not included, {path}, can't be used: {err}") from None


def is_this_card(model: Model, card: Card) -> bool:
    """Whether `model` is `card`: one the user added from a card of that name (any file).
    Names compare in any case, as ngspice reads them. A stock model of the same id is our
    own card, never this one (none of these ship, D-288)."""
    return model.yours and model.info.source.card.lower() == card.card.lower()


def catalogue_entries(listing: NotIncluded, models: ModelLibrary) -> list[dict[str, Any]]:
    """The parts list's *not included* entries (origin `excluded`), in `Model.catalogue_entry`'s
    shape plus `why`, `get` (the download in words), `url` and `card`; a card already in
    `models` is left out, since its own entry shows instead."""
    present = [models.get(i) for i in models.ids()]
    return [
        _entry(c, listing.sources[c.source])
        for c in listing.cards
        if not any(is_this_card(m, c) for m in present)
    ]


def _entry(c: Card, reason: Reason) -> dict[str, Any]:
    return {
        "id": c.id, "type": c.type, "description": c.description, "maker": c.maker,
        "origin": "excluded", "origin_detail": "", "datasheet": "", "package": "",
        "sheet": "", "figure": "", "note": "", "checks": 0, "unchecked": [],
        "why": reason.why, "get": reason.get.format(file=c.file), "url": c.url, "card": c.card,
    }  # fmt: skip
