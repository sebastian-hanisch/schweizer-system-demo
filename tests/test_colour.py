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


def test_allocate_alternates_to_the_most_recent_game_in_which_the_colours_differed():
    # Regressionstest (echter, gegen bbpPairings gefundener Fehler, ~1,5 % aller Paare): Art. 5.2.3 heißt
    # "Alternate the colours to the most recent time in which one player had White and the other Black",
    # nicht "jeder wechselt zu seiner eigenen letzten Farbe". Beide haben hier nach 4 Runden Differenz 0 und
    # zuletzt Weiß (also mild Schwarz); die jüngste Gegenüberstellung mit verschiedenen Farben ist Runde 2
    # (Spieler 1: Schwarz, Spieler 4: Weiß) - also bekommt jetzt Spieler 1 Weiß. Die alte Fassung ließ
    # 5.2.3 hier ins Leere laufen und gab dem Höherrangigen (1) Schwarz.
    one = _p(1, [(11, "w"), (12, "b"), (13, "b"), (14, "w")])
    four = _p(4, [(21, "b"), (22, "w"), (23, "b"), (24, "w")])
    assert classify(one).strength == MILD and classify(four).strength == MILD
    pairing = allocate(one, four)
    assert (pairing.white, pairing.black) == (1, 4)
    swapped = allocate(four, one)
    assert (swapped.white, swapped.black) == (1, 4)


def test_allocate_alternation_compares_played_games_not_round_numbers():
    # bbpPairings' `findFirstColorDifference` (common.cpp) stellt in JEDER Historie die k-te jüngste
    # GESPIELTE Partie gegenüber, Freilose übersprungen - nicht Runde gegen Runde. Spieler 11 hatte ein
    # Freilos in Runde 1, Spieler 7 in Runde 3; beide haben gespielt w, b, w (nur anders verteilt) und
    # beide wollen STARK Schwarz. Nach gespielten Partien gibt es nie einen Unterschied, also entscheidet
    # 5.2.4: Spieler 7 (Score 2,0) ist höherrangig als 11 (1,5) und bekommt Schwarz. Nach Rundennummern
    # läge der Unterschied in Runde 2 (11: Weiß, 7: Schwarz) und 11 bekäme fälschlich Schwarz.
    eleven = Player(rank=11, score=1.5, games=tuple(
        GameRecord(i + 1, opp, col, 0.5, counted_as_bye=col is None)
        for i, (opp, col) in enumerate([(0, None), (30, "w"), (31, "b"), (32, "w")])
    ))
    seven = Player(rank=7, score=2.0, games=tuple(
        GameRecord(i + 1, opp, col, 0.5, counted_as_bye=col is None)
        for i, (opp, col) in enumerate([(33, "w"), (34, "b"), (0, None), (35, "w")])
    ))
    assert classify(eleven).strength == STRONG and classify(seven).strength == STRONG
    pairing = allocate(eleven, seven)
    assert (pairing.white, pairing.black) == (11, 7)


def test_allocate_same_unresolved_preference_grants_to_higher_score_not_just_higher_rank():
    # Regressionstest (echter, gegen bbpPairings.exe gefundener Bug, project_turnierplanung_dag_
    # scoping.md 2026-09-29): "höherrangig" in Art. 5.2.4 bedeutet Art.-1.2-Reihenfolge (Score
    # absteigend, dann Rang aufsteigend) - NICHT reinen Rangvergleich. bbpPairings' eigenes
    # `acceleratedScoreRankCompare` (dutch.cpp:488-514/tournament.h:242-254) vergleicht zuerst nach
    # Score. Mit GLEICHEM Score fallen beide Vergleiche zusammen (deshalb blieb der Fehler in jedem
    # bisherigen, nur nach Score-Gruppen sortierten Test unbemerkt) - hier bewusst UNTERSCHIEDLICHER
    # Score (ein aus einer höheren Bracket hereingefloateter Spieler mit besserem Score, aber
    # SCHLECHTEREM Rang, gegen einen score-niedrigeren mit besserem Rang): beide wollen (mild)
    # Schwarz, keine gemeinsame Farbhistorie löst den Gleichstand. Der score-HÖHERE (12), nicht der
    # rang-bessere (4), muss seine Präferenz bekommen.
    worse_rank_better_score = Player(rank=12, score=2.0, games=(GameRecord(1, 30, "b", 1.0, counted_as_bye=False), GameRecord(2, 31, "w", 1.0, counted_as_bye=False)))
    better_rank_worse_score = Player(rank=4, score=1.0, games=(GameRecord(1, 32, "b", 0.0, counted_as_bye=False), GameRecord(2, 33, "w", 1.0, counted_as_bye=False)))
    assert classify(worse_rank_better_score).strength == MILD and classify(worse_rank_better_score).colour == BLACK
    assert classify(better_rank_worse_score).strength == MILD and classify(better_rank_worse_score).colour == BLACK
    pairing = allocate(better_rank_worse_score, worse_rank_better_score)
    assert pairing.black == worse_rank_better_score.rank
    assert pairing.white == better_rank_worse_score.rank


# --- Abgleich der Farben mit bbpPairings ------------------------------------------------------

import os
import random

import pytest

import ss_engine
from ss_model import Pairing, RoundResult
from ss_oracle_bbppairings import run_bbppairings

EXE_PATH = os.environ.get("BBPPAIRINGS_EXE")


@pytest.mark.skipif(not EXE_PATH, reason="BBPPAIRINGS_EXE nicht gesetzt - Oracle-Tests übersprungen")
def test_colour_allocation_equals_bbppairings_on_its_own_pairings():
    """Die Farbzuteilung ist von der Paarungssuche getrennt (`allocate` bekommt ein fertiges Paar). Deshalb
    wird hier auf den Paarungen der Referenz selbst verglichen: so zählt jede Abweichung als Farbfehler und
    nicht als Folge einer anderen Paarung. Exakt, ohne Toleranz - gemessen 0 Abweichungen auf 5068 Paaren
    (8-31 Spieler, 5-9 Runden); davor, mit der alten Fassung von Art. 5.2.3, 76 (1,5 %)."""
    pairs_checked = 0
    for n in (8, 11, 14, 17):
        for rounds in (5, 9):
            for seed in range(3):
                rng = random.Random(seed * 1000 + n * 10 + rounds)
                players = {r: Player(rank=r) for r in range(1, n + 1)}
                for rnd in range(1, rounds + 1):
                    try:
                        theirs, bye = run_bbppairings(players, rnd, exe_path=EXE_PATH, total_rounds=rounds)
                    except RuntimeError:
                        break  # kleines Feld erschöpft - auch die Referenz findet keine Paarung mehr
                    for white, black in theirs:
                        mine = allocate(players[white], players[black])
                        assert (mine.white, mine.black) == (white, black), f"n={n} R={rounds} s={seed} rnd={rnd}"
                        pairs_checked += 1
                    result = RoundResult(rnd, tuple(Pairing(w, b) for w, b in theirs), bye, {})
                    outcomes = {w: rng.choice((True, False, None)) for w, _ in theirs}
                    players = ss_engine.apply_round(players, result, outcomes)
    assert pairs_checked > 500
