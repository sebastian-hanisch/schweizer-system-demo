"""Farbpräferenz-Klassifikation (Art. 1.7) und Zuteilung (Art. 5.2)."""

from __future__ import annotations

from ss_colour import ABSOLUTE, MILD, NONE, STRONG, allocate, classify
from ss_model import BLACK, GameRecord, Player, WHITE


def _p(rank, games):
    grecs = tuple(GameRecord(i + 1, opp, col, 1.0, counted_as_bye=False) for i, (opp, col) in enumerate(games))
    return Player(rank=rank, score=0.0, games=grecs)


def test_no_games_is_none_preference():
    pref = classify(Player(rank=1))
    assert pref.strength == NONE
    assert pref.colour is None


def test_mild_preference_alternates_from_last_colour():
    p = _p(1, [(2, "w"), (3, "b")])  # ein Weiss, ein Schwarz -> diff=0 -> MILD, alterniert von Schwarz
    pref = classify(p)
    assert pref.strength == MILD
    assert pref.colour == WHITE


def test_single_game_gives_strong_not_mild_preference():
    # EIN Spiel -> Differenz zwangsläufig +-1 -> STRONG, nicht MILD (MILD braucht diff=0, also
    # mindestens zwei Partien mit je einer Farbe).
    p = _p(1, [(2, "w")])
    pref = classify(p)
    assert pref.strength == STRONG
    assert pref.colour == BLACK


def test_two_whites_in_a_row_gives_absolute_preference():
    p = _p(1, [(2, "w"), (3, "w")])  # zwei Weiss-Partien in Folge -> absolute Schwarz-Präferenz
    pref = classify(p)
    assert pref.strength == ABSOLUTE
    assert pref.colour == BLACK


def test_absolute_preference_can_coexist_with_diff_one():
    # b,w,w -> Differenz -1+1+1=+1 (für sich STARK), ABER letzte zwei Partien beide Weiss ->
    # das ABSOLUTE-Kriterium (Art. 1.7.1, zweite Bedingung) hat Vorrang vor der reinen Differenz.
    p = _p(1, [(2, "b"), (3, "w"), (4, "w")])
    pref = classify(p)
    assert pref.strength == ABSOLUTE


def test_absolute_preference_same_colour_last_two():
    p = _p(1, [(2, "w"), (3, "b"), (4, "b")])  # letzte zwei = b,b -> absolute Weiss-Präferenz
    pref = classify(p)
    assert pref.strength == ABSOLUTE
    assert pref.colour == WHITE


def test_allocate_grants_both_preferences_when_compatible():
    a = _p(1, [(9, "w")])  # mild, prefers black
    b = _p(2, [(9, "b")])  # mild, prefers white
    pairing = allocate(a, b)
    assert pairing.white == 2 and pairing.black == 1


def test_allocate_symmetric_regardless_of_argument_order():
    a = _p(1, [(9, "w")])
    b = _p(2, [(9, "b")])
    p1 = allocate(a, b)
    p2 = allocate(b, a)
    assert (p1.white, p1.black) == (p2.white, p2.black)


def test_allocate_stronger_preference_wins_on_conflict():
    # absolute: letzte zwei Partien beide Weiss -> ABSOLUTE Präferenz für Schwarz.
    absolute_black = _p(1, [(9, "b"), (8, "w"), (7, "w")])
    assert classify(absolute_black).strength == ABSOLUTE and classify(absolute_black).colour == BLACK
    # mild-schwarz-präferenz erzeugen: zwei Partien, gleich viele je Farbe, zuletzt Weiss gespielt.
    mild_black = _p(2, [(9, "b"), (8, "w")])
    assert classify(mild_black).strength == MILD and classify(mild_black).colour == BLACK
    # beide wollen SCHWARZ -> echter Konflikt, die stärkere (ABSOLUTE) Präferenz gewinnt.
    pairing = allocate(absolute_black, mild_black)
    assert pairing.black == absolute_black.rank
    assert pairing.white == mild_black.rank


def test_allocate_falls_back_to_rank_when_no_preferences():
    a = Player(rank=1)
    b = Player(rank=2)
    pairing = allocate(a, b)
    # höherrangiger (kleinere Nummer) mit ungerader Nummer -> bekommt Weiss
    assert pairing.white == 1


def test_allocate_falls_back_to_rank_even_numbers():
    a = Player(rank=2)
    b = Player(rank=3)
    pairing = allocate(a, b)
    # höherrangiger ist 2 (gerade) -> bekommt Schwarz, 3 bekommt Weiss
    assert pairing.white == 3
    assert pairing.black == 2


def test_allocate_same_unresolved_strong_preference_grants_to_higher_rank():
    # Regressionstest (echter, gegen bbpPairings.exe gefundener Bug): beide Spieler haben je EIN
    # Weiss-Spiel gewonnen (diff=+1 -> STARKE Schwarz-Präferenz), keine gemeinsame Historie, also
    # weder 5.2.1 (verschiedene Farben) noch 5.2.2 (unterschiedliche Stärke) noch 5.2.3 (Alternierung
    # löst nichts, da beide zu Schwarz alternieren wollen). Art. 5.2.4 verlangt: der höherrangige
    # Spieler (1) bekommt SEINE (=ihre gemeinsame) Präferenz - hier fälschlich übersprungen und
    # direkt zu 5.2.5 (reine Paritätsregel) gesprungen, was Spieler 1 WEISS statt SCHWARZ gab.
    higher = _p(1, [(9, "w")])
    lower = _p(4, [(8, "w")])
    assert classify(higher).strength == STRONG and classify(higher).colour == BLACK
    assert classify(lower).strength == STRONG and classify(lower).colour == BLACK
    pairing = allocate(higher, lower)
    assert pairing.black == higher.rank
    assert pairing.white == lower.rank
