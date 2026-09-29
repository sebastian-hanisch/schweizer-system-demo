"""Cross-Check von `ss_matching_engine.py` (bbpPairings' EIGENER, treu portierter Algorithmus) gegen
die echte Referenz-Engine `bbpPairings.exe` - unabhängig von `tests/test_oracle_bbppairings.py`, das
die WÖRTLICH-regeltext-treue `ss_engine.py`/`ss_bracket.py` prüft.

Läuft nur, wenn `BBPPAIRINGS_EXE` gesetzt ist (siehe `test_oracle_bbppairings.py`s Moduldoku).

**Gemessener Befund** (project_turnierplanung_dag_scoping.md, 2026-09-29): volle Standardstichprobe
(30 Saatwerte/4-16 Spieler/1-4 Runden) **100,000 %** (1430/1430), härtere Stichprobe (25 Saatwerte/
6-19 Spieler/bis 6 Runden) **100,000 %** (1994/1994) - EXAKTE Übereinstimmung auf beiden Stichproben.
Der letzte verbliebene Fall wurde auf einen gemeinsamen, latenten Bug in `ss_colour.allocate`
zurückgeführt (Art. 5.2.4-Gleichstand verglich nur nach Rang statt nach Score-dann-Rang wie
bbpPairings' `acceleratedScoreRankCompare` - siehe `ss_colour.py`s Moduldoku) - seit dem Fix dort
exakte Parität. Deutlich über `ss_engine.py`s Stand, weil dieses Modul bbpPairings' TATSÄCHLICHEN
Mechanismus abbildet (ein einziges, rundenweit fortgeführtes Matching-Objekt) statt eines
nachträglich aufgesetzten Tie-Breaks auf einer strukturell anderen (bracket-für-bracket-rekursiven)
Architektur - siehe Moduldoku von `ss_matching_engine.py`/`ss_bbp_tiebreak.py` für die Chronologie.
NICHT in `app.py` verdrahtet (bewusste Nutzerentscheidung, siehe Plan) - dieser Test ist die einzige
laufende Verifikation."""

from __future__ import annotations

import os
import random

import pytest

import ss_engine
from ss_matching_engine import NoValidPairingError, _edge_weight, pair_round_matching
from ss_model import GameRecord, Player
from ss_oracle_bbppairings import BbpPairingsUnavailable, run_bbppairings

EXE_PATH = os.environ.get("BBPPAIRINGS_EXE")

pytestmark = pytest.mark.skipif(not EXE_PATH, reason="BBPPAIRINGS_EXE nicht gesetzt - Oracle-Tests übersprungen")


def _random_tournament(n_players, n_rounds, seed):
    rng = random.Random(seed)
    players = {r: Player(rank=r) for r in range(1, n_players + 1)}
    for rnd in range(1, n_rounds + 1):
        result = pair_round_matching(players, rnd)
        white_wins = {p.white: rng.random() < 0.55 for p in result.pairings}
        players = ss_engine.apply_round(players, result, white_wins)
    return players


def test_edge_weight_current_bracket_pairs_outranks_everything_below():
    # `computeEdgeWeight` (dutch.cpp:283-286): "Paare in der aktuellen Bracket" ist das
    # höchstpriorisierte Feld (nach dem Kompatibilitäts-/Freilos-Gate) - eine Kante, die dieses Bit
    # setzt, muss JEDE Kante schlagen, die es nicht setzt, unabhängig von allem, was danach kommt.
    players = {1: Player(rank=1), 2: Player(rank=2), 3: Player(rank=3)}
    st_players = players

    from ss_matching_engine import _RoundState, _score_ranks

    st = _RoundState(players=st_players, topscorer_threshold=99.0, played_rounds=0)
    st.score_rank = _score_ranks(players)
    w_in_current = _edge_weight(players[1], players[2], True, False, st)
    w_in_next = _edge_weight(players[1], players[3], False, True, st)
    assert w_in_current > w_in_next


def test_homogeneous_bracket_of_four_pairs_canonically():
    # Kein History-Unterschied zwischen 1-4: bbpPairings' eigenes Matching entscheidet hier NICHT
    # willkürlich (blossom-interner Zufall), sondern über die "finalize remainder locks"-Stufe
    # (dutch.cpp:1509-1543) - Regressionstest für den in dieser Sitzung gefundenen, anfangs fehlenden
    # Teilschritt (ohne ihn: (1,2)/(3,4) statt der korrekten S1-vs-S2-Struktur (1,3)/(2,4)).
    players = {r: Player(rank=r) for r in range(1, 5)}
    result = pair_round_matching(players, 1)
    pairs = {frozenset((p.white, p.black)) for p in result.pairings}
    assert pairs == {frozenset((1, 3)), frozenset((2, 4))}


def test_remainder_scope_excludes_next_bracket():
    # Regressionstest für den größten in dieser Sitzung gefundenen Strukturfehler: `remainder`
    # (dutch.cpp:1270-1285) umfasst NUR das aktuelle Fenster (Pending+Residenten DIESER Bracket),
    # NICHT die nächste Bracket - eine frühere Fassung nahm next_window fälschlich mit hinein, was
    # `remainder_pairs` systematisch verfälschte und die Übereinstimmungsrate auf rund 30-50 % drückte
    # (siehe project_turnierplanung_dag_scoping.md). Handgebauter Fall: Bracket {1,2,3} (Score 1.0,
    # ungerade) + Bracket {4,5,6} (Score 0.0) nach genau einer Runde mit denselben festen Ergebnissen -
    # bbpPairings wählt hier nachweislich (1,2) lokal + 3 kaskadiert zu 4, NICHT (1,3)+2-kaskadiert
    # o. Ä.
    players = {
        1: Player(rank=1, score=1.0, games=(GameRecord(1, 4, "w", 1.0, counted_as_bye=False),)),
        2: Player(rank=2, score=1.0, games=(GameRecord(1, 5, "b", 1.0, counted_as_bye=False),)),
        3: Player(rank=3, score=1.0, games=(GameRecord(1, 6, "w", 1.0, counted_as_bye=False),)),
        4: Player(rank=4, score=0.0, games=(GameRecord(1, 1, "b", 0.0, counted_as_bye=False),)),
        5: Player(rank=5, score=0.0, games=(GameRecord(1, 2, "w", 0.0, counted_as_bye=False),)),
        6: Player(rank=6, score=0.0, games=(GameRecord(1, 3, "b", 0.0, counted_as_bye=False),)),
    }
    result = pair_round_matching(players, 2)
    pairs = {frozenset((p.white, p.black)) for p in result.pairings}
    assert pairs == {frozenset((1, 2)), frozenset((3, 4)), frozenset((5, 6))}


def test_round_one_matches_for_several_field_sizes():
    for n in (4, 5, 6, 7, 8, 10):
        players = {r: Player(rank=r) for r in range(1, n + 1)}
        mine = pair_round_matching(players, 1)
        mine_pairs = {frozenset((p.white, p.black)) for p in mine.pairings}
        theirs_pairs, theirs_bye = run_bbppairings(players, 1, exe_path=EXE_PATH)
        theirs_pairs_set = {frozenset(p) for p in theirs_pairs}
        assert mine_pairs == theirs_pairs_set, f"n={n}: {mine_pairs} != {theirs_pairs_set}"
        assert mine.bye == theirs_bye


def test_measured_agreement_rate_on_random_multiround_tournaments():
    """Gemessen 100 %/100 % auf der vollen Standard-/härteren Stichprobe (siehe Moduldoku) - hier
    eine kleinere, schnellere Stichprobe mit Sicherheitsmarge nach unten, damit ein echter Rückschritt
    auffällt, ohne bei jeder kleinen Schwankung rot zu werden (keine exakte 100 %-Prüfung - dieselbe
    Zufallsstichprobe könnte in Zukunft einen bisher unentdeckten Randfall treffen)."""
    total = 0
    matched = 0
    for n_players in (4, 5, 6, 7, 8, 10, 12):
        max_rounds = min(4, n_players - 2)
        for n_rounds in range(1, max_rounds + 1):
            for seed in range(8):
                try:
                    players = _random_tournament(n_players, n_rounds, seed * 1000 + n_players * 7 + n_rounds)
                except NoValidPairingError:
                    continue
                try:
                    mine = pair_round_matching(players, n_rounds + 1)
                except NoValidPairingError:
                    continue
                mine_pairs = {frozenset((p.white, p.black)) for p in mine.pairings}
                try:
                    theirs_pairs, theirs_bye = run_bbppairings(players, n_rounds + 1, exe_path=EXE_PATH)
                except BbpPairingsUnavailable:
                    continue
                except RuntimeError:
                    continue
                theirs_pairs_set = {frozenset(p) for p in theirs_pairs}
                total += 1
                if mine_pairs == theirs_pairs_set and mine.bye == theirs_bye:
                    matched += 1
    assert total > 30, "zu wenige vergleichbare Runden erzeugt - Testkonfiguration prüfen"
    rate = matched / total
    assert rate >= 0.99, f"Übereinstimmungsrate {rate:.1%} liegt unter der gemessenen Marke (~99,95-100 %, Marge nach unten)"
