"""Cross-Check des schlanken Blossom-Kerns gegen networkx.max_weight_matching (Test-Orakel,
nie zur Laufzeit importiert) und gegen Brute Force auf kleinen Graphen."""

from __future__ import annotations

import itertools
import random

import networkx as nx
import pytest

from ss_blossom import max_weight_perfect_matching, maximum_cardinality_matching


def _adj_from_edges(n, edges):
    adj = [[] for _ in range(n)]
    for i, j in edges:
        adj[i].append(j)
        adj[j].append(i)
    return adj


def _brute_force_best_perfect_matching(n, weight):
    if n % 2 != 0:
        return None
    best = None
    vertices = list(range(n))

    def backtrack(remaining, acc):
        nonlocal best
        if not remaining:
            if best is None or acc > best:
                best = acc
            return
        v = remaining[0]
        rest = remaining[1:]
        for k, w in enumerate(rest):
            pair_key = (v, w) if v < w else (w, v)
            if pair_key in weight:
                backtrack(rest[:k] + rest[k + 1:], acc + weight[pair_key])

    backtrack(vertices, 0)
    return best


def test_k4_matches_hand_verified_weighted_blossom_example():
    # Aus wb_blossom.py's eigener Dokumentation: K4 mit Kosten 01:3,02:13,03:11,12:22,13:24,23:30 -
    # billigste (Minimierung!) Paarung ist {0,1}+{2,3} = 33. Hier MAXIMIEREN wir stattdessen (unser
    # Anwendungsfall will das größte C9-C21-Gewicht), darum als Gewinn-Gewichte verwendet: das Ergebnis
    # mit dem GROESSTEN Gesamtgewicht ist dann die Paarung {1,2}+{0,3} = 22+11 = ... zur Kontrolle per
    # Brute Force, nicht angenommen.
    n = 4
    adj = _adj_from_edges(n, [(0, 1), (0, 2), (0, 3), (1, 2), (1, 3), (2, 3)])
    weight = {(0, 1): 3, (0, 2): 13, (0, 3): 11, (1, 2): 22, (1, 3): 24, (2, 3): 30}
    mate = max_weight_perfect_matching(n, adj, weight)
    pairs = {(i, mate[i]) if i < mate[i] else (mate[i], i) for i in range(n)}
    assert len(pairs) == 2
    total = sum(weight[p] for p in pairs)
    expected = _brute_force_best_perfect_matching(n, weight)
    assert total == expected


@pytest.mark.parametrize("trial", range(80))
def test_random_small_graphs_match_networkx(trial):
    rng = random.Random(trial)
    n = rng.choice([4, 6, 8, 10])
    edges = [(i, j) for i in range(n) for j in range(i + 1, n) if rng.random() < 0.6]
    # Sicherstellen, dass überhaupt eine perfekte Paarung existiert: volle Kante ergänzen, falls nötig.
    g_check = nx.Graph()
    g_check.add_nodes_from(range(n))
    g_check.add_edges_from(edges)
    if not nx.is_perfect_matching(g_check, nx.max_weight_matching(g_check, maxcardinality=True)):
        edges = [(i, j) for i in range(n) for j in range(i + 1, n)]  # vollständiger Graph als Rückfall

    weight = {(i, j): rng.randint(1, 50) for i, j in edges}
    adj = _adj_from_edges(n, edges)

    mate = max_weight_perfect_matching(n, adj, weight)
    assert len(mate) == n
    pairs = {(i, mate[i]) if i < mate[i] else (mate[i], i) for i in range(n)}
    assert len(pairs) == n // 2
    our_total = sum(weight[p] for p in pairs)

    g = nx.Graph()
    g.add_nodes_from(range(n))
    for (i, j), w in weight.items():
        g.add_edge(i, j, weight=w)
    nx_pairs_raw = nx.max_weight_matching(g, maxcardinality=True)
    nx_pairs = {(i, j) if i < j else (j, i) for i, j in nx_pairs_raw}
    nx_total = sum(weight[p] for p in nx_pairs)

    assert len(nx_pairs) == n // 2, "Testinstanz hat keine perfekte Paarung - Testaufbau prüfen"
    assert our_total == nx_total


def test_odd_n_rejected():
    with pytest.raises(ValueError):
        max_weight_perfect_matching(3, [[1, 2], [0, 2], [0, 1]], {(0, 1): 1, (0, 2): 1, (1, 2): 1})


def test_no_perfect_matching_raises():
    # 4 Knoten, aber nur eine Kante - keine perfekte Paarung möglich.
    adj = [[1], [0], [], []]
    with pytest.raises(ValueError):
        max_weight_perfect_matching(4, adj, {(0, 1): 5})


def test_maximum_cardinality_matching_finds_perfect_matching_when_one_exists():
    n = 4
    adj = _adj_from_edges(n, [(0, 1), (2, 3), (0, 2), (1, 3)])
    mate = maximum_cardinality_matching(n, adj)
    assert len(mate) == 4


def test_maximum_cardinality_matching_leaves_exactly_one_unmatched_on_odd_star():
    # Ein Stern (0 ist mit allen anderen verbunden, sonst keine Kanten) - maximal 1 Paar, 1 Rest.
    n = 5
    adj = [[1, 2, 3, 4], [0], [0], [0], [0]]
    mate = maximum_cardinality_matching(n, adj)
    assert len(mate) == 2  # ein Paar = 2 Knoten gematcht, 3 unmatched


def test_maximum_cardinality_matching_empty_graph():
    n = 3
    adj = [[], [], []]
    assert maximum_cardinality_matching(n, adj) == {}


def test_prefers_higher_weight_over_alternative_perfect_matching():
    # Zwei disjunkte Paarungsmöglichkeiten auf 4 Knoten: {0,1}+{2,3} (Gewicht 1+1=2) vs.
    # {0,2}+{1,3} (Gewicht 100+100=200) - der Löser muss die zweite wählen.
    n = 4
    adj = _adj_from_edges(n, [(0, 1), (2, 3), (0, 2), (1, 3)])
    weight = {(0, 1): 1, (2, 3): 1, (0, 2): 100, (1, 3): 100}
    mate = max_weight_perfect_matching(n, adj, weight)
    pairs = {(i, mate[i]) if i < mate[i] else (mate[i], i) for i in range(n)}
    assert pairs == {(0, 2), (1, 3)}
