"""Which supply powers the circuit (D-143, D-185): the Power menu's (a wall wart into the
DC jack), a battery part, or both.

The Power menu's rails are ideal sources on their nets. With a battery and no DC plug in
(an unplugged DC jack, or none), the battery powers the positive rails its + reaches (on
the rail, or on the DC jack's battery lug with the jack's + on it, as a real pedal is
wired, 9c): those rails' sources are off. A battery whose + reaches no rail is just a
supply on its own net, and the Power menu keeps every rail. Negative rails (a charge
pump's, a ± supply) stay. With a DC plug in, the adapter powers it, and the battery is
cut off only when its + goes through the DC jack's battery lug, as wired (D-185): wired
anywhere else it stays connected beside the adapter. With a DC jack drawn and no plug in,
the Power menu's supply isn't there: its rails are held at 0 V, as a cut-off battery's
are (D-359).

No power (D-359): each supply is on or off by the plugs in its path (`power_cuts` names
what cut each), and the pedal has no power when no supply that's on feeds anything.
"""

from contextlib import suppress
from dataclasses import dataclass
from typing import Literal

from solum.circuit.cables import (
    battery_cut_off,
    battery_cutter,
    plug_said,
    plugs,
    silence,
    switching_jacks,
)
from solum.circuit.connectivity import ConnectivityError, Nets, connect
from solum.circuit.schema import SUPPLY_SIGNS, Battery, Circuit, DcJack, Guitar, Jack, VSource
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
    """The positive rails the battery takes over when it powers the circuit (`_reached`);
    none while the wiring contradicts itself (two labels joined mid-edit: the view still
    draws it and says why, D-335)."""
    global _last
    last = _last
    if last is not None and last[0] is circuit:
        return last[1]
    rails: frozenset[str] = frozenset()
    if _battery(circuit) is not None:
        with suppress(ConnectivityError):
            rails = _reached(circuit, connect(circuit))
    _last = (circuit, rails)
    return rails


def on_battery(circuit: Circuit) -> Battery | None:
    """The battery when it powers the circuit: no DC plug in, and its + reaches a rail
    (9c: on a net of its own it powers only that net). Else None."""
    jack = _dc_jack(circuit)
    if (jack is not None and jack.plugged) or not battery_rails(circuit):
        return None
    return _battery(circuit)


def adapter_on(circuit: Circuit) -> bool:
    """Whether the Power menu's supply is there: always with no DC jack drawn, else only
    with a plug in it (D-359)."""
    jack = _dc_jack(circuit)
    return jack is None or jack.plugged


@dataclass(frozen=True)
class Cut:
    """A supply a plug (or a missing one) cuts off: the jack, why as a message says it,
    and what to do."""

    ref: str
    said: str  # "DC has no plug in"
    fix: str  # "plug DC in"


def power_cuts(circuit: Circuit) -> list[Cut]:
    """Each supply cut off by what's in a jack (D-359): the Power menu's by a DC jack with
    no plug in, the battery by a jack's ring with no mono plug in (D-354). A battery cut
    off by a DC plug isn't listed: the adapter is in."""
    cuts = []
    jack = _dc_jack(circuit)
    if jack is not None and not jack.plugged:
        cuts.append(Cut(jack.ref, f"{jack.ref} has no plug in", f"plug {jack.ref} in"))
    ring = battery_cutter(circuit)
    if ring is not None and (jack is None or not jack.plugged or not _lug_wired(circuit)):
        said = f"{ring.ref} {plug_said(ring)}, so its battery is cut off"
        cuts.append(Cut(ring.ref, said, f"put a mono cable in {ring.ref}"))
    return cuts


def _lug_wired(circuit: Circuit) -> bool:
    with suppress(ConnectivityError):
        return battery_wiring(circuit, connect(circuit)) == "lug"
    return False


def powered_off(circuit: Circuit) -> bool:
    """A plug cuts a supply off and no supply that's on feeds anything (D-354, D-357,
    D-359): no DC source, no part but the battery and the DC jack on a rail the Power
    menu holds while its plug is in, nor on the net a battery that's on holds (its rail,
    or a net of its own). The pedal is off, so its operating point says nothing about its
    bias."""
    if not power_cuts(circuit) or any(isinstance(p, VSource) for p in circuit.parts):
        return False
    try:
        nets = connect(circuit)
    except ConnectivityError:
        return False
    held = set(live_rails(circuit)) if adapter_on(circuit) else set()
    battery = battery_of(circuit, nets)
    if battery is not None and not battery_cut_off(circuit):
        held |= battery_rails(circuit) or {nets.net_of(battery.ref, "+")}
    power = {p.ref for p in circuit.parts if isinstance(p, (Battery, DcJack))}
    return not any(ref not in power for net in held for ref, _ in nets.members.get(net, ()))


def no_power(circuit: Circuit) -> str | None:
    """Why the pedal has no power (`powered_off`), naming each plug that cut a supply off,
    or None (D-358, D-359). The banner, the curves, the scope and every DC reading say it
    instead of a result."""
    if not powered_off(circuit):
        return None
    said = " and ".join(c.said for c in power_cuts(circuit))
    return f"The pedal has no power: {said}."


def no_power_refs(circuit: Circuit) -> list[str]:
    """The jacks that leave the pedal without power, for the banner to select (D-359)."""
    return [c.ref for c in power_cuts(circuit)] if powered_off(circuit) else []


def drawable(circuit: Circuit) -> bool:
    """Whether the curves, the scope and live curves can be drawn: a guitar input and some
    power (D-358). A cable out of a powered pedal doesn't stop them: they come from a test
    signal, and the circuit is there to measure."""
    return any(isinstance(p, Guitar) for p in circuit.parts) and no_power(circuit) is None


def render_refusal(circuit: Circuit) -> str | None:
    """Why a render can't be made, with what to do, or None (D-354, D-358): the input's or
    the output's cable out (nothing would reach the amp), or no power."""
    if out := silence(circuit):
        return f"{out} Put its cable in (Knobs) to render."
    if off := no_power(circuit):
        fix = " or ".join(c.fix for c in power_cuts(circuit))
        return f"{off} {fix[0].upper()}{fix[1:]} (Knobs) to render."
    return None


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
    """The rails the Power menu's ideal sources hold, and at what voltage: all of them, or
    on a battery all but the ones it takes over (`battery_rails`); at 0 V with a DC jack
    unplugged (`adapter_on`, D-359), so nothing makes up a supply there."""
    rails = dict(circuit.power.rails)
    if on_battery(circuit) is not None:
        taken = battery_rails(circuit)
        rails = {name: volts for name, volts in rails.items() if name not in taken}
    return rails if adapter_on(circuit) else dict.fromkeys(rails, 0.0)


def supply_volts(circuit: Circuit) -> dict[str, float]:
    """Each rail's voltage as the circuit sees it: the Power menu's (0 V unplugged), or on
    a battery alone its voltage for the positive rails (before any drop in its wiring)."""
    found = live_rails(circuit)
    battery = on_battery(circuit)
    if battery is not None:
        # a cable out (D-354): the rails it holds are dead
        volts = 0.0 if battery_cut_off(circuit) else parse_value(battery.volts)
        found |= dict.fromkeys(battery_rails(circuit), volts)
    return {name: found[name] for name in circuit.power.rails}


def power_chip(circuit: Circuit) -> dict[str, object] | None:
    """What the header's chip beside the Power menu says (D-145): "Battery · 7.4 V" while
    the battery alone powers the circuit (the menu greyed: it isn't used), "DC jack" while
    the jack does (the menu sets its voltage). With both, one entry per position of the DC
    jack's Power switch (0 plugged in, 1 the battery), so the chip follows the switch.
    None with neither."""
    jack = _dc_jack(circuit)
    if jack is None and on_battery(circuit) is None:
        return None
    chip = _chip(circuit)
    if jack is not None:  # its Power switch is always in Knobs (D-359)
        chip = {
            "control": jack.ref,
            "positions": [_chip(circuit.with_part(jack.ref, plugged=on)) for on in (True, False)],
        }
    cuts = _cable_cuts(circuit)
    return {**chip, "cut_off": {"text": "Battery · cut off", "jacks": cuts}} if cuts else chip


def _cable_cuts(circuit: Circuit) -> dict[str, dict[str, object]]:
    """Each jack whose cable can cut the battery off (D-357): where its cable switch opens
    (`at`) and the positions that cut it off, so the chip follows the switch."""
    found: dict[str, dict[str, object]] = {}
    for ref in switching_jacks(circuit):
        jack = circuit.part(ref)
        assert isinstance(jack, Jack)
        options = plugs(jack)
        cut = [i for i, plug in enumerate(options)
               if battery_cut_off(circuit.with_part(ref, plug=plug))]  # fmt: skip
        if cut:
            found[ref] = {"at": options.index(jack.plug), "positions": cut}
    return found


def _chip(circuit: Circuit) -> dict[str, object]:
    battery = on_battery(circuit)
    if battery is None:
        text = "DC jack" if adapter_on(circuit) else "DC jack · unplugged"
        return {"text": text, "battery": False}
    return {"text": f"Battery · {parse_value(battery.volts):g} V", "battery": True}
