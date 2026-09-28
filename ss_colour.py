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

    # 5.2.3: zur zuletzt gespielten Farbe alternieren (pro Spieler betrachtet).
    alt_a = _opposite(a.last_colour) if a.last_colour else None
    alt_b = _opposite(b.last_colour) if b.last_colour else None
    if alt_a is not None and alt_b is not None and alt_a != alt_b:
        # Beide alternieren zu verschiedenen Farben - konfliktfrei erfüllbar.
        return Pairing(white=a.rank, black=b.rank) if alt_a == WHITE else Pairing(white=b.rank, black=a.rank)

    # 5.2.4: beide wollen (nach 5.2.1-5.2.3 unaufgelöst) dieselbe Farbe - der höherrangige Spieler
    # bekommt SEINE (=ihre gemeinsame) Präferenz erfüllt. NICHT dieselbe Regel wie 5.2.5 (die gilt
    # nur, wenn WEDER Spieler überhaupt eine Präferenz hat, s. Aufruf oben in 5.2.1).
    higher, lower = (a, b) if a.rank < b.rank else (b, a)
    if pa.colour == WHITE:
        return Pairing(white=higher.rank, black=lower.rank)
    return Pairing(white=lower.rank, black=higher.rank)


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
