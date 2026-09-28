"""C1 (keine Wiederholung) + C3 (absolute Farbpräferenz-Kollision, mit Spitzenreiter-Ausnahme).

`compatible(a, b)` entscheidet nur, ob eine KANTE überhaupt existiert - C1/C3 werden nie bewertet,
nur durch das Fehlen der Kante erzwungen (wie im echten bbpPairings-Quellcode: `compatible()` gibt
schlicht False zurück, kein "Strafgewicht").
"""

from __future__ import annotations

from ss_colour import ABSOLUTE, classify
from ss_model import Player


def compatible(a: Player, b: Player, topscorer_threshold: float) -> bool:
    """`topscorer_threshold` = die Hälfte der maximal möglichen Punktzahl (Art. 1.8: "Topscorers ...
    have a score of OVER 50 % of the maximum possible score") - NICHT der aktuell höchste Score im
    Feld (realer, gegen bbpPairings.exe gefundener Bug: "Spitzenreiter" ist ein fester Schwellwert
    relativ zur Gesamtrundenzahl, keine Gleichheit mit dem Turnier-Höchststand). Art. 2.1.3 [C3]:
    "Non-topscorers ... shall not meet" - die Einschränkung gilt nur für ein Paar aus ZWEI
    Nicht-Spitzenreitern; ist MINDESTENS einer der beiden Spitzenreiter, greift C3 gar nicht erst."""
    if b.rank in a.opponents:  # C1
        return False

    pref_a, pref_b = classify(a), classify(b)
    if pref_a.strength == ABSOLUTE and pref_b.strength == ABSOLUTE and pref_a.colour == pref_b.colour:
        either_topscorer = a.score > topscorer_threshold or b.score > topscorer_threshold
        if not either_topscorer:  # C3, mit Spitzenreiter-Ausnahme
            return False

    return True
