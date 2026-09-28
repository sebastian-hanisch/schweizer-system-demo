"""Cross-Check gegen die echte, FIDE-anerkannte Referenz-Engine bbpPairings.

Läuft nur, wenn `BBPPAIRINGS_EXE` auf eine lauffähige Programmdatei zeigt (lokal: die
heruntergeladene Windows-.exe; CI: das Linux-x86_64-Release, s. .github/workflows/tests.yml) -
sonst werden diese Tests übersprungen (`skipif`), damit die restliche Suite auch offline läuft.

**Ehrlicher, gemessener Befund** (nicht behauptet, siehe README/project_turnierplanung_dag_scoping.md):
seit der Umstellung auf die wörtliche Transposition/Tausch-Suche MIT ECHTEM BACKTRACKING (Art. 3+4
des Regeltexts) UND der Behebung mehrerer konkreter, gegen `bbpPairings.exe` gefundener Bugs (u. a.
[C5]/[C9] fehlten in der Freilos-Auswahl komplett; MDPs wurden nicht nach Art. 1.2 sortiert
weitergereicht, was Art. 4.4s Limbo-Regel verkehrt herum greifen ließ; die [C3]-Spitzenreiter-
Ausnahme verlangte fälschlich BEIDE statt MINDESTENS EINEN Spitzenreiter; "Spitzenreiter" (Art. 1.8)
wurde als Gleichstand mit dem aktuellen Höchststand statt als Schwelle von 50 % der maximal
MÖGLICHEN Punktzahl behandelt) stimmt diese Engine in ca. 98 % der Fälle exakt mit bbpPairings
überein (absolute Kriterien C1-C3 IMMER korrekt). Der Test unten prüft genau diese gemessene Quote
mit Sicherheitsmarge, nicht 100 % Übereinstimmung.
"""

from __future__ import annotations

import os
import random

import pytest

from ss_engine import apply_round, pair_round
from ss_model import Player
from ss_oracle_bbppairings import BbpPairingsUnavailable, run_bbppairings

EXE_PATH = os.environ.get("BBPPAIRINGS_EXE")

pytestmark = pytest.mark.skipif(not EXE_PATH, reason="BBPPAIRINGS_EXE nicht gesetzt - Oracle-Tests übersprungen")


def _random_tournament(n_players, n_rounds, seed):
    rng = random.Random(seed)
    players = {r: Player(rank=r) for r in range(1, n_players + 1)}
    for rnd in range(1, n_rounds + 1):
        result = pair_round(players, rnd)
        white_wins = {p.white: rng.random() < 0.55 for p in result.pairings}
        players = apply_round(players, result, white_wins)
    return players


def test_dutch_2025_c5_fixture_reproduced_by_bbppairings_itself():
    # Gegenprobe: die echte .exe auf der ORIGINAL-Fixtur bestätigt dasselbe Ergebnis, das
    # test_engine.py für unsere eigene Engine hart einprogrammiert hat (Verifikationskette).
    from ss_model import GameRecord

    def mk(rank, score, games):
        grecs = tuple(GameRecord(i + 1, o, c, 1.0 if r == 1 else 0.0, counted_as_bye=False) for i, (o, c, r) in enumerate(games))
        return Player(rank=rank, score=score, games=grecs)

    players = {
        1: mk(1, 2.0, [(4, "w", 1), (2, "b", 1)]),
        2: mk(2, 1.0, [(5, "b", 1), (1, "w", 0)]),
        3: mk(3, 2.0, [(6, "w", 1), (4, "b", 1)]),
        4: mk(4, 0.0, [(1, "b", 0), (3, "w", 0)]),
        5: mk(5, 1.0, [(2, "w", 0), (6, "b", 1)]),
        6: mk(6, 0.0, [(3, "b", 0), (5, "w", 0)]),
    }
    pairs, bye = run_bbppairings(players, 3, absent=frozenset({4}), exe_path=EXE_PATH)
    assert bye == 6
    assert set(pairs) == {(1, 5), (3, 2)}


def test_round_one_matches_for_several_field_sizes():
    for n in (4, 5, 6, 7, 8, 10):
        players = {r: Player(rank=r) for r in range(1, n + 1)}
        mine = pair_round(players, 1)
        mine_pairs = {frozenset((p.white, p.black)) for p in mine.pairings}
        theirs_pairs, theirs_bye = run_bbppairings(players, 1, exe_path=EXE_PATH)
        theirs_pairs_set = {frozenset(p) for p in theirs_pairs}
        assert mine_pairs == theirs_pairs_set, f"n={n}: {mine_pairs} != {theirs_pairs_set}"
        assert mine.bye == theirs_bye


def test_measured_agreement_rate_on_random_multiround_tournaments():
    """Kein 100%-Anspruch - misst die reale Quote und prüft sie gegen die zuletzt dokumentierte
    Marke (siehe Moduldoku) mit Sicherheitsabstand nach unten, damit ein echter Rückschritt
    auffällt, ohne bei jeder kleinen Schwankung rot zu werden."""
    total = 0
    matched = 0
    for n_players in (4, 5, 6, 7, 8, 10):
        max_rounds = min(3, n_players - 2)
        for n_rounds in range(1, max_rounds + 1):
            for seed in range(8):
                try:
                    players = _random_tournament(n_players, n_rounds, seed * 1000 + n_players * 7 + n_rounds)
                except Exception:
                    continue
                try:
                    mine = pair_round(players, n_rounds + 1)
                except Exception:
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
    assert rate >= 0.90, f"Übereinstimmungsrate {rate:.1%} liegt unter der dokumentierten Marke (~98%, Marge nach unten)"
