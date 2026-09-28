"""Bausteine der Qualitätskriterien C10-C21 (Art. 2.4, handbook.fide.com/chapter/C0403202602) -
reine Bewertungsfunktionen für EIN Paar bzw. EINEN Spieler. `ss_bracket.py` summiert diese über
alle Paare/Downfloater eines Kandidaten zu einem Vergleichstupel (0 = keine Verletzung = besser,
direkter Tupel-Vergleich, KEINE gemischt-radix-Kodierung nötig - anders als im vorherigen,
globalen-Matching-Ansatz, wo C9-C21 in EIN Kantengewicht gepresst werden mussten)."""

from __future__ import annotations

from ss_colour import STRONG, allocate, classify
from ss_model import DOWN, Player, UP


def colour_terms(a: Player, b: Player, topscorer_threshold: float) -> tuple[int, int, int, int]:
    """(C10, C11, C12, C13) für EIN Paar (a, b), Farbe wie `ss_colour.allocate` sie tatsächlich
    vergäbe. C10/C11 zählen nur bei Spitzenreitern (Art. 1.8: Score > `topscorer_threshold`, der
    Hälfte der maximal möglichen Punktzahl - NICHT Gleichheit mit dem aktuellen Höchststand);
    C12/C13 für beide Spieler."""
    pairing = allocate(a, b)
    white, black = (a, b) if pairing.white == a.rank else (b, a)

    diff_w = white.colour_difference + 1
    diff_b = black.colour_difference - 1

    c10 = 0
    if white.score > topscorer_threshold and abs(diff_w) > 2:
        c10 += 1
    if black.score > topscorer_threshold and abs(diff_b) > 2:
        c10 += 1

    def three_in_a_row(player: Player, new_colour: str) -> bool:
        last_two = player.last_two_colours
        return len(last_two) == 2 and last_two[0] == last_two[1] == new_colour

    c11 = 0
    if white.score > topscorer_threshold and three_in_a_row(white, "w"):
        c11 += 1
    if black.score > topscorer_threshold and three_in_a_row(black, "b"):
        c11 += 1

    pref_a, pref_b = classify(a), classify(b)
    got_a = "w" if a is white else "b"
    got_b = "w" if b is white else "b"

    def unmet(pref, got: str) -> int:
        return int(pref.colour is not None and pref.colour != got)

    def unmet_strong(pref, got: str) -> int:
        return int(pref.strength in (STRONG, "absolute") and pref.colour is not None and pref.colour != got)

    c12 = unmet(pref_a, got_a) + unmet(pref_b, got_b)
    c13 = unmet_strong(pref_a, got_a) + unmet_strong(pref_b, got_b)
    return c10, c11, c12, c13


def downfloat_repeat_terms(player: Player) -> tuple[int, int]:
    """(C14, C16): 1, wenn `player` (residenter Downfloater dieser Runde) schon letzte bzw.
    vorletzte Runde downfloatete."""
    last, prev = (player.float_in_last_n_rounds(2) + (None, None))[:2]
    return (1 if last == DOWN else 0), (1 if prev == DOWN else 0)


def upfloat_repeat_terms(player: Player) -> tuple[int, int]:
    """(C15, C17): 1, wenn `player` (residenter MDP-Gegner dieser Runde, bekommt also selbst einen
    Upfloat) schon letzte bzw. vorletzte Runde upfloatete."""
    last, prev = (player.float_in_last_n_rounds(2) + (None, None))[:2]
    return (1 if last == UP else 0), (1 if prev == UP else 0)
