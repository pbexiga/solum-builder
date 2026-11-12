"""Which supply powers the circuit (D-143, D-185): the Power menu's (a wall wart into the
DC jack), a battery part, or both.

The Power menu's rails are ideal sources on their nets. With a battery and no DC plug in
(an unplugged DC jack, or none), the battery powers the positive rails its + reaches (on
the rail, or on the DC jack's battery lug with the jack's + on it, as a real pedal is
wired, 9c): those rails' sources are off. A battery whose + reaches no rail is just a
supply on its own net, and the Power menu keeps every rail. Negative rails (a charge
pump's, a ± supply) stay. With a DC plug in, the adapter powers it, and the battery is
cut off only when its + goes through the DC jack's battery lug, as wired (D-185): wired
anywhere else it stays connected beside the adapter.
"""

from typing import Literal

from solum.circuit.connectivity import Nets, connect
from solum.circuit.schema import SUPPLY_SIGNS, Battery, Circuit, DcJack
from solum.units import parse_value


def _battery(circuit: Circuit) -> Battery | None:
    return next((p for p in circuit.parts if isinstance(p, Battery)), None)


def _dc_jack(circuit: Circuit) -> DcJack | None:
    return next((p for p in circuit.parts if isinstance(p, DcJack)), None)


def _reached(circuit: Circuit, nets: Nets) -> frozenset[str]:
    """The positive rail the battery's + reaches as wired (9c): V+ when it's on it, or on
    the DC jack's battery lug with the jack's + on it (the lug touches the sleeve with no
    plug in), whether or not the Power menu sets V+."""
    battery, jack = _battery(circuit), _dc_jack(circuit)
    if battery is None:
        return frozenset()
    plus = nets.net_of(battery.ref, "+")
    if jack is not None and plus == nets.net_of(jack.ref, "sw"):
        plus = nets.net_of(jack.ref, "+")
    return frozenset({plus}) if SUPPLY_SIGNS.get(plus, 0) > 0 else frozenset()


# the last circuit asked about and its rails: `on_battery` is asked many times a run
_last: tuple[Circuit, frozenset[str]] | None = None


def battery_rails(circuit: Circuit) -> frozenset[str]:
    """The positive rails the battery takes over when it powers the circuit (`_reached`)."""
    global _last
    last = _last
    if last is not None and last[0] is circuit:
        return last[1]
    rails = _reached(circuit, connect(circuit)) if _battery(circuit) is not None else frozenset()
    _last = (circuit, rails)
    return rails


def on_battery(circuit: Circuit) -> Battery | None:
    """The battery when it powers the circuit: no DC plug in, and its + reaches a rail
    (9c: on a net of its own it powers only that net). Else None."""
    jack = _dc_jack(circuit)
    if (jack is not None and jack.plugged) or not battery_rails(circuit):
        return None
    return _battery(circuit)


BatteryWiring = Literal["alone", "lug", "beside", "apart"]


def battery_wiring(circuit: Circuit, nets: Nets) -> BatteryWiring | None:
    """How the battery is wired (D-185, 9c): `apart` when its + reaches no rail (a supply
    on its own net; the Power menu keeps V+), `alone` with no DC jack (it powers the
    circuit), `lug` with its + on the DC jack's battery lug (a plug cuts it off), `beside`
    with its + on a rail beside a DC jack (it stays connected beside a plug). None with no
    battery."""
    battery, jack = _battery(circuit), _dc_jack(circuit)
    if battery is None:
        return None
    if not _reached(circuit, nets):
        return "apart"
    if jack is None:
        return "alone"
    return "lug" if nets.net_of(battery.ref, "+") == nets.net_of(jack.ref, "sw") else "beside"


def battery_of(circuit: Circuit, nets: Nets) -> Battery | None:
    """The battery connected now: on its own, or beside a DC plug when its + doesn't go
    through the DC jack's battery lug (D-185). None when there's none or the plug cuts
    it off."""
    jack = _dc_jack(circuit)
    if jack is not None and jack.plugged and battery_wiring(circuit, nets) == "lug":
        return None
    return _battery(circuit)


def live_rails(circuit: Circuit) -> dict[str, float]:
    """The rails the Power menu's ideal sources hold: all of them, or on a battery all but
    the ones it takes over (`battery_rails`)."""
    rails = circuit.power.rails
    if on_battery(circuit) is None:
        return dict(rails)
    taken = battery_rails(circuit)
    return {name: volts for name, volts in rails.items() if name not in taken}


def supply_volts(circuit: Circuit) -> dict[str, float]:
    """Each rail's voltage as the circuit sees it: the Power menu's, or on a battery alone
    its voltage for the positive rails (before any drop in its wiring)."""
    battery = on_battery(circuit)
    if battery is None:
        return dict(circuit.power.rails)
    volts, taken = parse_value(battery.volts), battery_rails(circuit)
    return {name: (volts if name in taken else v) for name, v in circuit.power.rails.items()}


def power_chip(circuit: Circuit) -> dict[str, object] | None:
    """What the header's chip beside the Power menu says (D-145): "Battery · 7.4 V" while
    the battery alone powers the circuit (the menu greyed: it isn't used), "DC jack" while
    the jack does (the menu sets its voltage). With both, one entry per position of the DC
    jack's Power switch (0 plugged in, 1 the battery), so the chip follows the switch.
    None with neither."""
    jack = _dc_jack(circuit)
    if jack is None and on_battery(circuit) is None:
        return None
    if jack is not None and _battery(circuit) is not None:
        return {
            "control": jack.ref,
            "positions": [_chip(circuit.with_part(jack.ref, plugged=on)) for on in (True, False)],
        }
    return _chip(circuit)


def _chip(circuit: Circuit) -> dict[str, object]:
    battery = on_battery(circuit)
    if battery is None:
        return {"text": "DC jack", "battery": False}
    return {"text": f"Battery · {parse_value(battery.volts):g} V", "battery": True}
