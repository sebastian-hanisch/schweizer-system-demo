"""Farbpräferenz-Klassifikation und Art.-5.2-Farbzuteilung.

Reine Funktionen: die Zuteilung ist KEIN Suchproblem, sondern ein deterministischer Ablauf durch
eine feste Prioritätenliste, sobald das Paar bereits feststeht (die PaarungsSUCHE selbst entscheidet
nur, WER auf WEN trifft, s. `ss_bracket.py` - welche Farbe folgt danach, ein eigener Schritt).
"""

from __future__ import annotations

from dataclasses import dataclass

from ss_model import BLACK, WHITE, Pairing, Player

NONE, MILD, STRONG, ABSOLUTE = "none", "mild", "strong", "absolute"


@dataclass(frozen=True)
class ColourPreference:
    strength: str  # NONE, MILD, STRONG, ABSOLUTE
    colour: str | None  # WHITE, BLACK oder None (bei NONE)


def _opposite(colour: str) -> str:
    return BLACK if colour == WHITE else WHITE


def classify(player: Player) -> ColourPreference:
    last = player.last_colour
    if last is None:
        return ColourPreference(NONE, None)

    diff = player.colour_difference
    last_two = player.last_two_colours

    if len(last_two) == 2 and last_two[0] == last_two[1]:
        return ColourPreference(ABSOLUTE, _opposite(last_two[-1]))
    if diff > 1:
        return ColourPreference(ABSOLUTE, BLACK)
    if diff < -1:
        return ColourPreference(ABSOLUTE, WHITE)
    if diff == 1:
        return ColourPreference(STRONG, BLACK)
    if diff == -1:
        return ColourPreference(STRONG, WHITE)
    return ColourPreference(MILD, _opposite(last))


_STRENGTH_ORDER = {NONE: 0, MILD: 1, STRONG: 2, ABSOLUTE: 3}


def allocate(a: Player, b: Player) -> Pairing:
    """Art. 5.2, absteigende Priorität. `a`/`b` in beliebiger Reihenfolge; das Ergebnis ist
    unabhängig davon, welcher zuerst genannt wird (der Rang, nicht die Aufrufreihenfolge, entscheidet)."""
    pa, pb = classify(a), classify(b)

    # 5.2.1: beide Präferenzen gleichzeitig erfüllbar (verschiedene Farben gewünscht, oder
    # mindestens einer hat keine Präferenz).
    if pa.colour != pb.colour or pa.colour is None or pb.colour is None:
        if pa.colour == WHITE or pb.colour == BLACK:
            return Pairing(white=a.rank, black=b.rank)
        if pa.colour == BLACK or pb.colour == WHITE:
            return Pairing(white=b.rank, black=a.rank)
        # beide NONE: weiter zu 5.2.4/5.2.5 (kein Farbkonflikt aufzulösen, aber auch keine
        # Präferenz zu erfüllen - direkt zur Rang-/Paritätsregel springen)
        return _allocate_by_rank(a, b)

    # Ab hier: pa.colour == pb.colour (beide wollen dieselbe Farbe) - Konflikt.
    strength_a, strength_b = _STRENGTH_ORDER[pa.strength], _STRENGTH_ORDER[pb.strength]

    # 5.2.2: stärkere Präferenz gewinnt; bei zwei ABSOLUTEN die mit der größeren Farbdifferenz.
    if strength_a != strength_b:
        winner = a if strength_a > strength_b else b
        return _pairing_with_preference(a, b, winner, pa if winner is a else pb)
    if pa.strength == ABSOLUTE and pb.strength == ABSOLUTE:
        diff_a, diff_b = abs(a.colour_difference), abs(b.colour_difference)
        if diff_a != diff_b:
            winner = a if diff_a > diff_b else b
            return _pairing_with_preference(a, b, winner, pa if winner is a else pb)

    # 5.2.3: "Alternate the colours to the most recent time in which one player had White and the
    # other Black" - ein PAARvergleich über die Historie, nicht "jeder wechselt zu seiner eigenen
    # letzten Farbe" (frühere Fassung; gegen bbpPairings gemessen: ~1,5 % der Paare falsch, immer bei
    # gleich starker Präferenz).
    alternated = _alternate_to_last_difference(a, b)
    if alternated is not None:
        return alternated

    # 5.2.4: beide wollen (nach 5.2.1-5.2.3 unaufgelöst) dieselbe Farbe - der höherrangige Spieler
    # bekommt SEINE (=ihre gemeinsame) Präferenz erfüllt. NICHT dieselbe Regel wie 5.2.5 (die gilt
    # nur, wenn WEDER Spieler überhaupt eine Präferenz hat, s. Aufruf oben in 5.2.1).
    #
    # "Höherrangig" heißt hier Art.-1.2-Reihenfolge (Score absteigend, dann Rang aufsteigend) - NICHT
    # reiner Rangvergleich. Echter, gegen `bbpPairings.exe` gefundener Bug (project_turnierplanung_
    # dag_scoping.md, 2026-09-29): bei GLEICHEM Score (z. B. innerhalb einer homogenen Bracket)
    # stimmen beide Vergleiche überein, weshalb der Fehler durch KEINEN bisherigen Sweep auffiel (der
    # nur die PaarungsSTRUKTUR prüft, nie die Farbzuteilung) - bei UNTERSCHIEDLICHEM Score (z. B. ein
    # aus einer höheren Bracket hereingefloateter MDP gegen einen score-niedrigeren Residenten)
    # entscheidet bbpPairings' eigenes `acceleratedScoreRankCompare` NACHWEISLICH nach Score ZUERST,
    # Rang nur als Gleichstand-Kriterium (dutch.cpp:488-514, tournament.h:242-254) - reiner
    # Rangvergleich griff dann VERKEHRT herum.
    higher, lower = (a, b) if (-a.score, a.rank) < (-b.score, b.rank) else (b, a)
    if pa.colour == WHITE:
        return Pairing(white=higher.rank, black=lower.rank)
    return Pairing(white=lower.rank, black=higher.rank)


def _alternate_to_last_difference(a: Player, b: Player) -> Pairing | None:
    """Art. 5.2.3: wer in der jüngsten Gegenüberstellung der beiden Historien Weiß hatte, bekommt
    jetzt Schwarz. Gegenübergestellt wird so wie in bbpPairings' `findFirstColorDifference`
    (`common.cpp`): in JEDER Historie nur die tatsächlich gespielten Partien (Freilose übersprungen),
    von hinten gezählt - die k-te jüngste Partie des einen gegen die k-te jüngste des anderen, NICHT
    Runde gegen Runde mit derselben Nummer. Der Unterschied zählt nur bei Freilosen (Art. 3.4 der
    Allgemeinen Regeln: ungespielte Runden werden übergangen). `None`, wenn die kürzere Historie
    aufgebraucht ist, ohne dass sich die Farben je unterscheiden (dann entscheidet 5.2.4)."""
    played_a = [g.colour for g in reversed(a.games) if g.colour is not None]
    played_b = [g.colour for g in reversed(b.games) if g.colour is not None]
    for colour_a, colour_b in zip(played_a, played_b):
        if colour_a != colour_b:
            return Pairing(white=a.rank, black=b.rank) if colour_a == BLACK else Pairing(white=b.rank, black=a.rank)
    return None


def _pairing_with_preference(a: Player, b: Player, winner: Player, winner_pref: ColourPreference) -> Pairing:
    loser = b if winner is a else a
    if winner_pref.colour == WHITE:
        return Pairing(white=winner.rank, black=loser.rank)
    return Pairing(white=loser.rank, black=winner.rank)


def _allocate_by_rank(a: Player, b: Player) -> Pairing:
    # 5.2.4/5.2.5: der höherrangige Spieler (kleinere Startranglisten-Nummer) bekommt die
    # Anfangsfarbe Weiss bei ungerader eigener Nummer, sonst Schwarz.
    higher, lower = (a, b) if a.rank < b.rank else (b, a)
    if higher.rank % 2 == 1:
        return Pairing(white=higher.rank, black=lower.rank)
    return Pairing(white=lower.rank, black=higher.rank)
