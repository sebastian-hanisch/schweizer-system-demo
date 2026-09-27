"""C1 (keine Wiederholung) + C3 (absolute Farbpräferenz-Kollision, mit Spitzenreiter-Ausnahme).

`compatible(a, b)` entscheidet nur, ob eine KANTE überhaupt existiert - C1/C3 werden nie bewertet,
nur durch das Fehlen der Kante erzwungen (wie im echten bbpPairings-Quellcode: `compatible()` gibt
schlicht False zurück, kein "Strafgewicht").
"""

from __future__ import annotations

from ss_colour import ABSOLUTE, classify
from ss_model import Player


def compatible(a: Player, b: Player, top_scorer_score: float) -> bool:
    """`top_scorer_score` = höchster Score im aktuellen Turnierstand (für die C3-Spitzenreiter-
    Ausnahme: Spitzenreiter dürfen trotz gleicher absoluter Farbpräferenz aufeinandertreffen, wenn
    keine andere legale Paarung existiert - hier vereinfacht als 'beide haben den Topscore')."""
    if b.rank in a.opponents:  # C1
        return False

    pref_a, pref_b = classify(a), classify(b)
    if pref_a.strength == ABSOLUTE and pref_b.strength == ABSOLUTE and pref_a.colour == pref_b.colour:
        both_topscorers = a.score == top_scorer_score and b.score == top_scorer_score
        if not both_topscorers:  # C3, mit Spitzenreiter-Ausnahme
            return False

    return True
