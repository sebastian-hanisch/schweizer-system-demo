"""Test der reinen Kardinalitäts-Existenzprobe (`ss_bracket.py`s [C4]/[C8]-Hilfsfunktionen nutzen
sie), portiert aus `weighted-blossom-demo/wb_blossom.py`."""

from __future__ import annotations

from ss_blossom import maximum_cardinality_matching


def _adj_from_edges(n, edges):
    adj = [[] for _ in range(n)]
    for i, j in edges:
        adj[i].append(j)
        adj[j].append(i)
    return adj


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
