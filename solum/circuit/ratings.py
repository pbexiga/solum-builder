"""Capacitor voltage ratings (D-203, D-360): what's sold, what a supply calls for, and the
ratings *Use suggested ratings* fills in."""

from collections.abc import Mapping

from solum.circuit.connectivity import Nets
from solum.circuit.schema import POLARISED, Battery, Capacitor, Circuit
from solum.units import parse_value

CAP_MARGIN = 0.8  # a capacitor with more than this share of its rating across it is too close
CAP_RATINGS = (6.3, 10.0, 16.0, 25.0, 35.0, 50.0, 63.0, 100.0)  # volts: electrolytics sold
# the problems whose rows offer *Use suggested ratings* (D-360)
RATING_RULES = ("cap-no-rating", "cap-over-voltage", "cap-rating-close")


def cap_rating(volts: float) -> float | None:
    """The smallest rating sold with `volts` inside `CAP_MARGIN` of it (16 V for 9 V, 25 V
    for 18 V); None past the largest."""
    return next((r for r in CAP_RATINGS if volts <= CAP_MARGIN * r), None)


def supply_top(circuit: Circuit) -> float | None:
    """The highest supply the circuit can have, by its size: the Power menu's rails and the
    battery's voltage, whatever the plugs say (a rating is for when it's powered). None
    with neither."""
    found = [abs(v) for v in circuit.power.rails.values()]
    found += [parse_value(p.volts) for p in circuit.parts if isinstance(p, Battery)]
    return max(found, default=None)


def suggested_cap_rating(circuit: Circuit) -> float | None:
    """The rating an electrolytic or tantalum gets on choosing its type: `cap_rating` of
    `supply_top`, or None with no supply (D-360)."""
    top = supply_top(circuit)
    return cap_rating(top) if top else None


def cap_rating_view(circuit: Circuit) -> dict[str, object] | None:
    """The view's `cap_rating`: the rating to fill (`suggested_cap_rating`) and the kinds
    that take one, so the form keeps no list of its own (D-360). None with no supply."""
    volts = suggested_cap_rating(circuit)
    return None if volts is None else {"volts": volts, "kinds": list(POLARISED)}


def rating_fill(
    circuit: Circuit, nets: Nets, voltages: Mapping[str, float] | None
) -> dict[str, float]:
    """The ratings *Use suggested ratings* sets, by ref (D-360): every electrolytic and
    tantalum with none (`suggested_cap_rating`), and, with the DC (`voltages`), each one
    whose rating is under or too close to the DC across it (`cap_rating` of that). Film,
    ceramic and C0G stay as they are, and so does a rating that's fine."""
    fill: dict[str, float] = {}
    supply = suggested_cap_rating(circuit)
    for p in circuit.parts:
        if not isinstance(p, Capacitor) or p.kind not in POLARISED:
            continue
        if p.rating_v is None:
            if supply is not None:
                fill[p.ref] = supply
            continue
        if voltages is None:
            continue
        a, b = (voltages.get(nets.net_of(p.ref, pin)) for pin in ("1", "2"))
        if a is None or b is None:
            continue
        across = abs(a - b)
        better = cap_rating(across)
        if across > CAP_MARGIN * p.rating_v and better is not None:
            fill[p.ref] = better
    return fill
