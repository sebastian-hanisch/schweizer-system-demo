"""Regressionstests gegen die echten bbpPairings-Testfixturen (C5, C9) und Eigenschaftstests
für die absoluten Kriterien (C1-C3), die IMMER gelten müssen, unabhängig vom Cross-Check gegen
die Referenz-Engine."""

from __future__ import annotations

import random

import pytest

from ss_blossom import NoValidPairingError
from ss_engine import apply_round, pair_round
from ss_model import BYE, GameRecord, Player


def _mk(rank, score, games):
    grecs = tuple(
        GameRecord(i + 1, opp, col, 1.0 if res == 1 else 0.0, counted_as_bye=False)
        for i, (opp, col, res) in enumerate(games)
    )
    return Player(rank=rank, score=score, games=grecs, float_history=tuple(None for _ in games))


def test_dutch_2025_c5_fixture_matches_bbppairings_exactly():
    # Aus handbook.fide.com-Testfixtur dutch_2025_C5.input (bbpPairings-Repo), Hand-verifiziert -
    # siehe project_turnierplanung_dag_scoping.md für die vollständige Herleitung.
    players = {
        1: _mk(1, 2.0, [(4, "w", 1), (2, "b", 1)]),
        2: _mk(2, 1.0, [(5, "b", 1), (1, "w", 0)]),
        3: _mk(3, 2.0, [(6, "w", 1), (4, "b", 1)]),
        4: _mk(4, 0.0, [(1, "b", 0), (3, "w", 0)]),
        5: _mk(5, 1.0, [(2, "w", 0), (6, "b", 1)]),
        6: _mk(6, 0.0, [(3, "b", 0), (5, "w", 0)]),
    }
    result = pair_round(players, round_no=3, absent=frozenset({4}))
    pairs = {(p.white, p.black) for p in result.pairings}
    assert result.bye == 6
    assert pairs == {(1, 5), (3, 2)}


def test_dutch_2025_c9_fixture_matches_bbppairings_exactly():
    players = {
        1: _mk(1, 1.0, [(3, "w", 1)]),
        2: _mk(2, 1.0, [(4, "b", 1)]),
        3: _mk(3, 0.0, [(1, "b", 0)]),
        4: _mk(4, 0.0, [(2, "w", 0)]),
        5: Player(rank=5, score=0.0, games=(GameRecord(1, BYE, None, 0.0, counted_as_bye=True),), float_history=(None,)),
    }
    result = pair_round(players, round_no=2)
    pairs = {(p.white, p.black) for p in result.pairings}
    assert result.bye == 4
    assert pairs == {(2, 1), (3, 5)}


def test_round_one_fresh_field_uses_canonical_top_half_vs_bottom_half():
    # Empirisch an der echten bbpPairings.exe bestätigt (mit XXC white1): 6 Spieler ohne jede
    # Historie -> 1v4, 2v5, 3v6 (obere Hälfte gegen untere Hälfte in Rangreihenfolge).
    players = {r: Player(rank=r) for r in range(1, 7)}
    result = pair_round(players, round_no=1)
    pairs = {frozenset((p.white, p.black)) for p in result.pairings}
    assert pairs == {frozenset((1, 4)), frozenset((2, 5)), frozenset((3, 6))}
    assert result.bye is None


def test_round_one_odd_field_bye_goes_to_last_canonical_position():
    players = {r: Player(rank=r) for r in range(1, 6)}
    result = pair_round(players, round_no=1)
    pairs = {frozenset((p.white, p.black)) for p in result.pairings}
    assert pairs == {frozenset((1, 3)), frozenset((2, 4))}
    assert result.bye == 5


def _simulate(n_players, n_rounds, seed):
    """Spielt bis zu n_rounds Runden; bricht sauber ab, falls C1 für ein kleines Feld schon
    vorher erschöpft ist (echter, gültiger Zustand - kein Bug, s. test_no_valid_pairing_...)."""
    rng = random.Random(seed)
    players = {r: Player(rank=r) for r in range(1, n_players + 1)}
    history = []
    for rnd in range(1, n_rounds + 1):
        try:
            result = pair_round(players, rnd)
        except NoValidPairingError:
            break
        history.append(result)
        white_wins = {p.white: rng.random() < 0.55 for p in result.pairings}
        players = apply_round(players, result, white_wins)
    return players, history


@pytest.mark.parametrize("n_players", [4, 5, 6, 7, 8, 9, 11, 12])
@pytest.mark.parametrize("seed", range(10))
def test_c1_never_violated_across_a_short_tournament(n_players, seed):
    # C1: zwei Spieler treffen im ganzen Turnier nie zweimal aufeinander.
    max_rounds = min(4, n_players - 2)
    if max_rounds < 1:
        pytest.skip("Feld zu klein für mehrere Runden ohne C1-Erschöpfung")
    players, history = _simulate(n_players, max_rounds, seed * 97 + n_players)
    seen_pairs: set[frozenset[int]] = set()
    for result in history:
        for p in result.pairings:
            key = frozenset((p.white, p.black))
            assert key not in seen_pairs, f"Paar {key} spielt zweimal (n={n_players}, seed={seed})"
            seen_pairs.add(key)


@pytest.mark.parametrize("n_players", [5, 7, 9, 11])
@pytest.mark.parametrize("seed", range(10))
def test_c2_never_two_byes_for_the_same_player(n_players, seed):
    max_rounds = min(4, n_players - 2)
    players, history = _simulate(n_players, max_rounds, seed * 53 + n_players)
    byes = [r.bye for r in history if r.bye is not None]
    assert len(byes) == len(set(byes)), f"ein Spieler bekam zweimal ein Freilos (n={n_players}, seed={seed})"


@pytest.mark.parametrize("n_players", [4, 6, 8, 10])
@pytest.mark.parametrize("seed", range(10))
def test_round_cardinality_is_always_n_over_two_pairs(n_players, seed):
    max_rounds = min(3, n_players - 2)
    players, history = _simulate(n_players, max_rounds, seed * 31 + n_players)
    for result in history:
        n_active = n_players  # gerade Teilnehmerzahl, kein absent in diesem Test
        expected_pairs = n_active // 2 - (1 if result.bye is not None else 0)
        assert len(result.pairings) == expected_pairs


def test_no_valid_pairing_raises_clear_error_when_all_pairs_exhausted():
    # 4 Spieler, 3 Runden bereits gespielt -> alle C(4,2)=6 möglichen Paare sind erschöpft,
    # Runde 4 ist strukturell unmöglich (bestätigt: auch die echte bbpPairings.exe lehnt das ab).
    players, _ = _simulate(4, 3, seed=1)
    with pytest.raises(NoValidPairingError):
        pair_round(players, round_no=4)


def test_deterministic_same_input_same_output():
    players = {r: Player(rank=r) for r in range(1, 11)}
    r1 = pair_round(players, 1)
    r2 = pair_round(players, 1)
    assert r1.pairings == r2.pairings
    assert r1.bye == r2.bye
