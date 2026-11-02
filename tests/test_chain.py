"""Rundenlösung in zwei Phasen (`ss_chain`): [C5]-[C9] gegen erschöpfende Aufzählung.

Eigenschaftstest: auf kleinen Zufallsständen werden ALLE gültigen vollständigen Runden (C1/C3 verträglich, ein
Freilos nur bei ungerader Zahl und nur für Spieler ohne Freilos, C2) aufgezählt, und `solve_round` muss genau
eine mit dem kleinsten (Freilos-Schlüssel, [C6]/[C7] des ersten Blocks, [C6]/[C7] des zweiten Blocks) liefern: der
erste Block entscheidet nach [C6]/[C7], der zweite nur über [C8] (Art. 2.4.3: "in the following bracket", nicht
tiefer - tiefere Blöcke dürfen die Farbe und die Floats des aktuellen Blocks nicht überstimmen). Das Profil wird
hier unabhängig vom Modul aus den Paaren berechnet: je Score-Gruppe von oben nach unten (Zahl, Scores absteigend) der Spieler, die
aus dieser Gruppe herausfallen, also ein Score >= der Gruppe haben und einen Partner unterhalb davon (das
Freilos zählt als Partner unterhalb von allem)."""

import pytest

import ss_engine
from ss_chain import bye_key, solve_round
from ss_compat import compatible, topscorer_threshold_for_round
from ss_model import Player
from ss_scenario import generate_tournament


def _groups(players):
    by_score: dict[float, list[int]] = {}
    for rank, player in players.items():
        by_score.setdefault(player.score, []).append(rank)
    return [(score, sorted(ranks)) for score, ranks in sorted(by_score.items(), key=lambda kv: -kv[0])]


def _profile(pairs, bye, players, groups):
    spans = [(max(players[a].score, players[b].score), min(players[a].score, players[b].score)) for a, b in pairs]
    if bye is not None:
        spans.append((players[bye].score, float("-inf")))
    profile = []
    for score, _ in groups:
        leaving = sorted((high for high, low in spans if high >= score > low), reverse=True)
        profile.append((len(leaving), tuple(leaving)))
    return tuple(profile)


def _all_rounds(players, threshold):
    """Alle gültigen vollständigen Runden als (Paare, Freilos)."""
    ranks = sorted(players)
    odd = len(ranks) % 2 == 1

    def matchings(remaining):
        if not remaining:
            yield []
            return
        first, rest = remaining[0], remaining[1:]
        for i, other in enumerate(rest):
            if compatible(players[first], players[other], threshold):
                for tail in matchings(rest[:i] + rest[i + 1:]):
                    yield [(first, other)] + tail

    if not odd:
        for pairs in matchings(ranks):
            yield pairs, None
        return
    for bye in ranks:
        if players[bye].had_bye_or_equivalent:
            continue
        for pairs in matchings([r for r in ranks if r != bye]):
            yield pairs, bye


@pytest.mark.parametrize("n", [6, 7, 8, 9])
def test_solve_round_picks_the_lexicographically_best_chain(n):
    checked = 0
    for seed in range(14):
        for rounds in (2, 3, 4):
            players = generate_tournament(n, rounds, seed).players
            if any(len(p.games) != rounds for p in players.values()):
                continue  # Turnier brach vorzeitig ab
            round_no = rounds + 1
            threshold = topscorer_threshold_for_round(round_no, round_no)
            groups = _groups(players)
            options = [(bye_key(players[bye]) if bye else (-1, -1), _profile(pairs, bye, players, groups)[:2], pairs, bye)
                       for pairs, bye in _all_rounds(players, threshold)]
            result = solve_round(groups, players, threshold)
            if not options:
                assert result is None
                continue
            assert result is not None, f"n={n} seed={seed} rounds={rounds}: es gibt Runden, solve_round fand keine"
            pairs, bye = result
            best = min((key, profile) for key, profile, _, _ in options)
            got = (bye_key(players[bye]) if bye else (-1, -1), _profile(pairs, bye, players, groups)[:2])
            assert got == best, f"n={n} seed={seed} rounds={rounds}: {got} statt {best}"
            checked += 1
    assert checked >= 15


def test_solve_round_pairs_every_player_exactly_once():
    for n, rounds, seed in [(12, 4, 1), (13, 5, 2), (20, 6, 3)]:
        players = generate_tournament(n, rounds, seed).players
        threshold = topscorer_threshold_for_round(rounds + 1, rounds + 1)
        pairs, bye = solve_round(_groups(players), players, threshold)
        seen = [r for pair in pairs for r in pair] + ([bye] if bye is not None else [])
        assert sorted(seen) == sorted(players)
        assert all(b not in players[a].opponents for a, b in pairs)  # C1
        assert (bye is None) == (n % 2 == 0)
        if bye is not None:
            assert not players[bye].had_bye_or_equivalent  # C2


def test_round_one_matches_the_natural_pairing():
    players = {r: Player(rank=r) for r in range(1, 9)}
    pairs, bye = solve_round(_groups(players), players, topscorer_threshold_for_round(1, 5))
    assert bye is None
    assert {frozenset(p) for p in pairs} == {frozenset((1, 5)), frozenset((2, 6)), frozenset((3, 7)), frozenset((4, 8))}


def test_pair_round_uses_the_chain_solver_and_stays_deterministic():
    players = generate_tournament(16, 3, 11).players
    first = ss_engine.pair_round(players, 4, total_rounds=6)
    second = ss_engine.pair_round(players, 4, total_rounds=6)
    assert first == second
