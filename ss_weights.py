"""Gemischt-radix-Kodierung ALLER Kriterien C5-C21 als EINE Python-`int` je Kante - höchste
Priorität = signifikanteste Stelle. Die ganze Runde wird als EIN gewichtetes Matching über alle
aktiven Spieler PLUS einen virtuellen Freilos-Knoten gelöst (wie die echte Referenz-Engine
bbpPairings - siehe `project_turnierplanung_dag_scoping.md` für die Architekturbegründung: eine
sequenzielle Bracket-für-Bracket-Verarbeitung mit reiner Existenz-Probe ist NICHT äquivalent zur
echten C6-C9-Priorisierung, gemessen an ~39% Abweichung bei zufälligen Testrunden).

Python-`int` ist beliebig groß (kein Überlauf wie in C++), unterstützt aber normale Arithmetik -
direkt einsetzbar in `ss_blossom.py`s unveränderte Dualwert-Rechnung.

Tier-Reihenfolge (absteigende Priorität, wie im FIDE-Regelwerk):
  C5  (nur Freilos-Kanten): niedrigster Score des Freilos-Empfängers
  C6  (nur echte Kanten):   gleicher Score = kein Downfloat (1), sonst 0
  C7  (nur echte Kanten):   bei Downfloat: niedrigerer Score des Downfloaters bevorzugt
  C9  (nur Freilos-Kanten): wenigste ungespielte Partien des Freilos-Empfängers
  C10-C13 (echte Kanten):   Farbqualität (Spitzenreiter-Grenzen, Präferenzen)
  C15/C17/C19/C21 (echte Kanten): Wiederholte Float-Situation (Downfloat-Seite UND Upfloat-Seite)

C14/C16 (Downfloat-Wiederholung derselben Person) sind jetzt TEIL von C15/C17 (symmetrisch für
beide Seiten der Kante behandelt, da es in diesem globalen Modell keine separate "MDP-Auswahl"
mehr gibt, aus der man C14/C16 getrennt herleiten könnte - jede grenzüberschreitende Kante hat
GENAU zwei Seiten, Downfloater UND Upfloat-Gegner, beide mit eigener Wiederholungs-Historie).
"""

from __future__ import annotations

from ss_colour import ABSOLUTE, STRONG, allocate, classify
from ss_model import DOWN, UP, Player

BASE = 10_000_000
_HALF = BASE // 2
_NEUTRAL = BASE // 2  # Platzhalterwert für Tiers, die für diesen Kantentyp nicht gelten


def _clip(value: int) -> int:
    return max(0, min(BASE - 1, value))


def _colour_quality_terms(a: Player, b: Player, top_score: float) -> tuple[int, int, int, int]:
    """(C10, C11, C12, C13) auf Basis der Farbe, die `ss_colour.allocate` tatsächlich vergäbe."""
    pairing = allocate(a, b)
    white = a if pairing.white == a.rank else b
    black = b if white is a else a

    def diff_after(player: Player, got_white: bool) -> int:
        return player.colour_difference + (1 if got_white else -1)

    diff_w, diff_b = diff_after(white, True), diff_after(black, False)

    c10_ok = 1
    if white.score == top_score and abs(diff_w) > 2:
        c10_ok = 0
    if black.score == top_score and abs(diff_b) > 2:
        c10_ok = 0

    def three_in_a_row(player: Player, new_colour: str) -> bool:
        last_two = player.last_two_colours
        return len(last_two) == 2 and last_two[0] == last_two[1] == new_colour

    c11_ok = 1
    if white.score == top_score and three_in_a_row(white, "w"):
        c11_ok = 0
    if black.score == top_score and three_in_a_row(black, "b"):
        c11_ok = 0

    pref_a, pref_b = classify(a), classify(b)
    got_a = "w" if a is white else "b"
    got_b = "w" if b is white else "b"

    def unmet(pref, got) -> bool:
        return pref.colour is not None and pref.colour != got

    c12 = 2 - (int(unmet(pref_a, got_a)) + int(unmet(pref_b, got_b)))

    def unmet_strong(pref, got) -> bool:
        return pref.strength in (STRONG, ABSOLUTE) and pref.colour is not None and pref.colour != got

    c13 = 2 - (int(unmet_strong(pref_a, got_a)) + int(unmet_strong(pref_b, got_b)))

    return c10_ok, c11_ok, c12, c13


def _float_repeat_terms(downfloater: Player, upfloat_opponent: Player) -> tuple[int, int, int, int]:
    """(C15, C17, C19, C21): straft Wiederholungen derselben Float-Situation (downfloater
    floatet wieder / upfloat_opponent bekommt wieder einen hereingefloateten Gegner) in der
    letzten bzw. vorletzten Runde - symmetrisch für beide Seiten der Kante ausgewertet."""
    d_hist = downfloater.float_in_last_n_rounds(2)
    u_hist = upfloat_opponent.float_in_last_n_rounds(2)
    d_last, d_prev = (d_hist + (None, None))[:2]
    u_last, u_prev = (u_hist + (None, None))[:2]

    c15 = 0 if d_last == DOWN else 1
    c17 = 0 if d_prev == DOWN else 1
    c15b = 0 if u_last == UP else 1
    c17b = 0 if u_prev == UP else 1
    c15 = min(c15, c15b)
    c17 = min(c17, c17b)

    score_gap = int(abs(downfloater.score - upfloat_opponent.score) * 2)
    c19 = _clip(_HALF - score_gap) if c15 == 0 else _HALF
    c21 = _clip(_HALF - score_gap) if c17 == 0 else _HALF
    return c15, c17, c19, c21


def real_edge_weight(a: Player, b: Player, top_score: float, is_canonical_partner: bool = False) -> int:
    """Kantengewicht für eine Paarung zweier ECHTER Spieler (kein Freilos).

    `is_canonical_partner`: True, wenn (a, b) exakt die "obere Hälfte gegen untere Hälfte in
    Rangreihenfolge"-Paarung innerhalb ihrer eigenen Score-Gruppe ist (S1[i] gegen S2[i], die
    FIDE-Standardkonstruktion für eine homogene Bracket). Unterste Prioritätsstufe: greift nur,
    wenn ALLE anderen Kriterien (C6-C21) zwischen mehreren Paarungsmustern nicht unterscheiden -
    z. B. Runde 1 ohne jede Historie, wo bbpPairings empirisch bestätigt exakt dieses Muster
    wählt (1v4,2v5,3v6 bei 6 Spielern, nie eine andere Aufteilung)."""
    same_score = a.score == b.score
    c6 = 1 if same_score else 0

    if same_score:
        c7 = _HALF  # kein Downfloat auf dieser Kante - neutral, dominiert nicht über C6 hinaus
        c15, c17, c19, c21 = _HALF, _HALF, _HALF, _HALF
    else:
        downfloater, upfloater = (a, b) if a.score > b.score else (b, a)
        c7 = _clip(BASE - 1 - int(downfloater.score * 2))  # niedrigerer Score = größeres Gewicht
        c15, c17, c19, c21 = _float_repeat_terms(downfloater, upfloater)

    c10, c11, c12, c13 = _colour_quality_terms(a, b, top_score)
    structural = 1 if is_canonical_partner else 0

    terms = (_NEUTRAL, c6, c7, _NEUTRAL, c10, c11, c12, c13, c15, c17, c19, c21, structural)
    weight = 0
    for term in terms:
        weight = weight * BASE + _clip(term)
    return weight


def bye_edge_weight(candidate: Player) -> int:
    """Kantengewicht Freilos-Knoten <-> `candidate`: C5 (niedrigster Score) vor C9 (wenigste
    ungespielte Partien) - alle anderen Tiers neutral, da Farb-/Float-Kriterien für ein Freilos
    nicht gelten. Letzte Stelle (unterhalb aller FIDE-Kriterien): bei vollem Gleichstand bekommt
    der niedriger gesetzte (höhere Startranglisten-Nummer) Spieler das Freilos eher - empirisch
    aus dutch_2025_C9 bestätigt (zwei Score- UND C9-gleiche Kandidaten, bbpPairings wählt den
    mit der höheren Nummer)."""
    c5 = _clip(BASE - 1 - int(candidate.score * 2))
    c9 = _clip(BASE - 1 - candidate.unplayed_games)
    rank_tiebreak = _clip(candidate.rank)
    terms = (c5, _NEUTRAL, _NEUTRAL, c9, _NEUTRAL, _NEUTRAL, _NEUTRAL, _NEUTRAL, _NEUTRAL, _NEUTRAL, _NEUTRAL, _NEUTRAL, rank_tiebreak)
    weight = 0
    for term in terms:
        weight = weight * BASE + _clip(term)
    return weight
