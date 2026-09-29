"""Phase 0/1-Checkpoints für `ss_bbp_tiebreak.py`: Prioritäts-Kodierung (`_pack`), das gewichtete
Matching-Primitiv (`_weighted_matching`) und `edge_weight` gegen handgebaute Fälle - VOR jeder
Oracle-Prüfung (siehe project_turnierplanung_dag_scoping.md / Plan)."""

from __future__ import annotations

import ss_bbp_tiebreak as tb
from ss_bracket import BracketContext, Candidate, _quality_tuple, solve_bracket
from ss_model import GameRecord, Player


def _player(rank: int, score: float = 0.0, games: tuple = (), float_history: tuple = ()) -> Player:
    return Player(rank=rank, score=score, games=games, float_history=float_history)


def test_pack_respects_strict_priority_over_all_lower_fields() -> None:
    # kleinstmöglicher Wert bei both_current=1 muss größer sein als der GRÖSSTMÖGLICHE Wert bei
    # both_current=0 (unabhängig von allen niedrigeren Feldern) - das ist die Kerneigenschaft, die
    # die gesamte Kodierung tragen muss.
    worst_with_current = tb._pack((1, 0, 0, 0, 0, 0, 0, 0, 0, 0))
    best_without_current = tb._pack((0, 1, 2, 2, 2, 2, 1, 1, 1, 1))
    assert worst_with_current > best_without_current

    worst_with_next = tb._pack((0, 1, 0, 0, 0, 0, 0, 0, 0, 0))
    best_without_next = tb._pack((0, 0, 2, 2, 2, 2, 1, 1, 1, 1))
    assert worst_with_next > best_without_next

    worst_with_c10 = tb._pack((0, 0, 2, 0, 0, 0, 0, 0, 0, 0))
    best_without_c10 = tb._pack((0, 0, 1, 2, 2, 2, 1, 1, 1, 1))
    assert worst_with_c10 > best_without_c10


def test_pack_reserves_room_for_tiebreak_perturbation() -> None:
    base = tb._pack((1, 1, 2, 2, 2, 2, 1, 1, 1, 1))
    assert tb._pack((1, 1, 2, 2, 2, 2, 1, 1, 1, 1)) + 1 <= base + tb._TIEBREAK_ROOM // 2
    assert tb._pack((1, 1, 2, 2, 2, 2, 1, 1, 1, 1)) - 1 >= base - tb._TIEBREAK_ROOM // 2


def test_weighted_matching_textbook_triangle() -> None:
    # Klassisches Beispiel: Dreieck 1-2-3 mit Kantengewichten 1, 2, 3 - Matching kann höchstens EINE
    # Kante wählen (ungerade Knotenzahl), die schwerste (2-3, Gewicht 3) muss gewinnen.
    weights = {(1, 2): 1, (1, 3): 2, (2, 3): 3}

    def weight_fn(x: int, y: int) -> int | None:
        return weights.get((min(x, y), max(x, y)))

    mate = tb._weighted_matching([1, 2, 3], weight_fn)
    assert mate == {2: 3, 3: 2}


def test_weighted_matching_prefers_more_edges_when_weight_says_so() -> None:
    # 4 Knoten, ein perfektes Matching {1-2, 3-4} mit Summe 10 muss über einem unvollständigen
    # Matching {1-3} mit Gewicht 100 gewinnen können oder verlieren, je nach echten Gewichten -
    # hier bewusst so gewählt, dass die GRÖSSERE Gesamtsumme (perfektes Matching) gewinnt.
    weights = {(1, 2): 5, (3, 4): 5, (1, 3): 1, (2, 4): 1}

    def weight_fn(x: int, y: int) -> int | None:
        return weights.get((min(x, y), max(x, y)))

    mate = tb._weighted_matching([1, 2, 3, 4], weight_fn)
    assert mate == {1: 2, 2: 1, 3: 4, 4: 3}


def test_weighted_matching_is_deterministic() -> None:
    weights = {(1, 2): 7, (2, 3): 7, (1, 3): 7}

    def weight_fn(x: int, y: int) -> int | None:
        return weights.get((min(x, y), max(x, y)))

    results = [tb._weighted_matching([3, 1, 2], weight_fn) for _ in range(20)]
    assert all(r == results[0] for r in results)


def test_weighted_matching_handles_large_int_weights() -> None:
    # `_pack`-Werte können schnell sehr groß werden (mehrere Stellen je Kriterium) - hier explizit
    # geprüft, dass `networkx.max_weight_matching` mit großen Python-`int`-Gewichten exakt bleibt
    # (kein Float-Rundungsfallstrick).
    big = 10**12
    weights = {(1, 2): big + 1, (1, 3): big, (2, 3): 1}

    def weight_fn(x: int, y: int) -> int | None:
        return weights.get((min(x, y), max(x, y)))

    mate = tb._weighted_matching([1, 2, 3], weight_fn)
    assert mate == {1: 2, 2: 1}


def test_edge_weight_none_when_incompatible() -> None:
    p1 = _player(1, games=(GameRecord(round_no=1, opponent=2, colour="w", score=1.0, counted_as_bye=False),))
    p2 = _player(2, games=(GameRecord(round_no=1, opponent=1, colour="b", score=0.0, counted_as_bye=False),))
    players = {1: p1, 2: p2}
    assert tb.edge_weight(1, 2, players, topscorer_threshold=0.0, current_pool=frozenset({1, 2}), mdp_ranks=frozenset()) is None


def test_edge_weight_current_current_dominates_downfloat() -> None:
    p1, p2, p3, p4 = (_player(r) for r in (1, 2, 3, 4))
    players = {1: p1, 2: p2, 3: p3, 4: p4}
    current_pool = frozenset({1, 2})
    w_current = tb.edge_weight(1, 2, players, 0.0, current_pool, frozenset())
    w_downfloat = tb.edge_weight(1, 3, players, 0.0, current_pool, frozenset())
    w_next_next = tb.edge_weight(3, 4, players, 0.0, current_pool, frozenset())
    assert w_current is not None and w_downfloat is not None and w_next_next is not None
    assert w_current > w_next_next > w_downfloat


def test_edge_weight_mdp_does_not_downfloat_further() -> None:
    p1, p2 = _player(1), _player(2)
    players = {1: p1, 2: p2}
    # p1 ist MDP (schon aus der Bracket darüber hereingefloatet), p2 liegt in der NÄCHSTEN Bracket -
    # eine solche Kante ist außerhalb des Zwei-Bracket-Scopes (siehe Moduldoku) und darf nicht
    # existieren.
    assert tb.edge_weight(1, 2, players, 0.0, current_pool=frozenset({1}), mdp_ranks=frozenset({1})) is None


def test_current_only_solve_matches_solve_bracket_quality() -> None:
    # Phase-1-Checkpoint (Plan): ein `_weighted_matching`-Lauf NUR über die aktuelle Bracket (kein
    # `next_group_residents`) muss auf einer handgebauten heterogenen Bracket eine Paarung mit
    # DERSELBEN Qualität liefern wie `ss_bracket.solve_bracket`s eigener bester Kandidat -
    # Quer-Check zwischen den zwei unabhängigen Codepfaden, kein Byte-Vergleich der Paarung selbst
    # (mehrere Paarungen können dieselbe Qualität erreichen).
    players = {r: Player(rank=r, score=2.0 if r in (1, 2) else 1.0) for r in (1, 2, 3, 4)}
    ctx = BracketContext(players=players, topscorer_threshold=99.0)
    residents, mdps = [3, 4], [1, 2]

    own_best = next(iter(solve_bracket(residents, mdps, ctx)))
    own_quality = _quality_tuple(
        list(own_best.pairs), [r for r in own_best.downfloaters if r not in mdps], frozenset(mdps),
        players, ctx.topscorer_threshold,
    )

    current_pool = frozenset(residents) | frozenset(mdps)
    mdp_ranks = frozenset(mdps)

    def weight_fn(x: int, y: int):
        return tb.edge_weight(x, y, players, ctx.topscorer_threshold, current_pool, mdp_ranks)

    mate = tb._weighted_matching(current_pool, weight_fn)
    tb_pairs = [(a, b) for a, b in mate.items() if a < b]
    tb_downfloaters = sorted(current_pool - set(mate))
    tb_quality = _quality_tuple(
        tb_pairs, [r for r in tb_downfloaters if r not in mdps], mdp_ranks, players, ctx.topscorer_threshold,
    )
    assert tb_downfloaters == list(own_best.downfloaters)
    assert tb_quality == own_quality


def test_resolve_tie_smoke_no_crash_and_picks_a_tied_candidate() -> None:
    # Kein handverifiziertes Szenario (das folgt separat gegen den echten Oracle) - reiner
    # Rauch-Test: `resolve_tie` darf auf einer realistischen heterogenen Bracket + Restgruppe weder
    # abstuerzen noch etwas ausserhalb von `tied` zurueckgeben.
    players = {r: Player(rank=r, score=2.0 if r in (1, 2) else (1.0 if r in (3, 4, 5, 6) else 0.0)) for r in range(1, 9)}
    ctx = BracketContext(players=players, topscorer_threshold=99.0)
    residents, mdps, next_group = [3, 4, 5, 6], [1, 2], [7, 8]

    tied = list(solve_bracket(residents, mdps, ctx))
    assert tied  # muss mindestens einen Kandidaten liefern (Existenzgarantie)

    chosen = tb.resolve_tie(tied, residents, mdps, next_group, ctx)
    assert chosen is None or chosen in tied


def test_resolve_tie_none_without_next_group() -> None:
    players = {r: Player(rank=r, score=1.0) for r in (1, 2, 3, 4)}
    ctx = BracketContext(players=players, topscorer_threshold=99.0)
    tied = [Candidate(pairs=((1, 2), (3, 4)), downfloaters=())]
    assert tb.resolve_tie(tied, [1, 2, 3, 4], [], [], ctx) is None
