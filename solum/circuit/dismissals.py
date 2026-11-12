"""Dismissed problems (D-176): which ones a save keeps.

A dismissal names its problem by rule, refs and nets (`schema.Dismissal`); the browser
matches it to the Problems panel's list (`web/problems.js`). One that names a part or net
the circuit no longer has can never match again, so a save drops it. One whose parts are
all still there is kept, even while its problem doesn't occur: the problem may come back
(a knob turned, a part's kind changed back), and it should come back dismissed.
"""

from solum.circuit.connectivity import ConnectivityError, connect
from solum.circuit.schema import Circuit, Dismissal


def kept_dismissals(circuit: Circuit) -> Circuit:
    """The circuit without the dismissals that name a part or net it no longer has. While
    the wiring contradicts itself (no nets to look at), only the parts are checked."""
    if not circuit.dismissed:
        return circuit
    refs = {p.ref for p in circuit.parts}
    try:
        nets: set[str] | None = set(connect(circuit).members)
    except ConnectivityError:
        nets = None

    def live(d: Dismissal) -> bool:
        return set(d.refs) <= refs and (nets is None or set(d.nets) <= nets)

    kept = [d for d in circuit.dismissed if live(d)]
    if len(kept) == len(circuit.dismissed):
        return circuit
    return circuit.model_copy(update={"dismissed": kept})
