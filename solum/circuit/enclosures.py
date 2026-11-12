"""Enclosure sizes builders name (9d1, D-204): the outside size as the seller lists it, in
mm, length by width by height. The one owner; the build package and File → Properties read it."""

from dataclasses import dataclass


@dataclass(frozen=True)
class EnclosureSize:
    name: str
    length: float
    width: float
    height: float
    source: str

    @property
    def text(self) -> str:
        return f"{self.length:g} \u00d7 {self.width:g} \u00d7 {self.height:g} mm"


SIZES: tuple[EnclosureSize, ...] = (
    EnclosureSize("1590A", 92.5, 38.5, 31.0, "DigiKey, Hammond 1590A (122740)"),
    EnclosureSize("1590B", 112.0, 60.5, 31.0, "DigiKey, Hammond 1590B (131015)"),
    EnclosureSize("125B", 122.0, 66.0, 39.5, "Tayda Electronics, 125B style aluminium diecast"),
    EnclosureSize("1590BB", 119.5, 94.0, 34.0, "DigiKey, Hammond 1590BB (131016)"),
    EnclosureSize("1590XX", 145.0, 121.0, 39.0, "RS Components 225-6378, Hammond 1590XX"),
)
CUSTOM = "custom"


def size_of(name: str) -> EnclosureSize | None:
    return next((s for s in SIZES if s.name == name), None)
