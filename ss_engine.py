"""Orchestrierung: die GANZE Runde als EIN gewichtetes Matching über alle aktiven Spieler PLUS
einen virtuellen Freilos-Knoten (bei ungerader Anzahl) - wie die echte Referenz-Engine bbpPairings
(siehe `project_turnierplanung_dag_scoping.md`: eine sequenzielle Bracket-für-Bracket-Verarbeitung
ist NICHT äquivalent zur echten Kriterienpriorisierung, gemessen an einer signifikanten
Abweichungsrate bei zufälligen Testrunden - deshalb dieser globale Ansatz)."""

from __future__ import annotations

from ss_blossom import max_weight_perfect_matching
from ss_colour import allocate
from ss_compat import compatible
from ss_model import BYE, DOWN, GameRecord, Pairing, Player, RoundResult, UP
from ss_weights import bye_edge_weight, real_edge_weight

BYE_NODE_MARKER = -1  # interner Platzhalter, kein echter Spielerrang


def _canonical_partners(active_players: dict[int, Player], ranks: list[int]) -> dict[int, int]:
    """FIDE-Standardkonstruktion je homogener Score-Gruppe: obere Hälfte (Rang-aufsteigend)
    gegen untere Hälfte, Position für Position (S1[i] gegen S2[i]) - der Default, den
    bbpPairings verwendet, wenn kein anderes Kriterium zwischen Paarungsmustern unterscheidet
    (empirisch bestätigt an einer Runde-1-Probe ohne jede Historie: 6 Spieler -> 1v4,2v5,3v6)."""
    by_score: dict[float, list[int]] = {}
    for r in ranks:
        by_score.setdefault(active_players[r].score, []).append(r)

    partner: dict[int, int] = {}
    for group in by_score.values():
        group.sort()
        half = len(group) // 2
        for i in range(half):
            partner[group[i]] = group[half + i]
            partner[group[half + i]] = group[i]
    return partner


def pair_round(players: dict[int, Player], round_no: int, absent: frozenset[int] = frozenset()) -> RoundResult:
    """`absent`: Spieler, die für DIESE Runde vorab abgemeldet sind (TRF-Freilos-Anfrage, z. B.
    Code "Z" = Null-Punkte-Freilos auf eigenen Wunsch) - bleiben im Turnier, werden aber in dieser
    Runde nicht gepaart."""
    active_players = {r: p for r, p in players.items() if r not in absent}
    ranks = sorted(active_players)
    n_real = len(ranks)
    top_score = max((p.score for p in active_players.values()), default=0.0)

    has_bye_node = n_real % 2 == 1
    n_nodes = n_real + (1 if has_bye_node else 0)
    index_of = {r: i for i, r in enumerate(ranks)}
    bye_node_index = n_real if has_bye_node else None

    canonical_partner = _canonical_partners(active_players, ranks)

    adj: list[list[int]] = [[] for _ in range(n_nodes)]
    weight: dict[tuple[int, int], int] = {}

    for i, ri in enumerate(ranks):
        for j in range(i + 1, n_real):
            rj = ranks[j]
            if compatible(active_players[ri], active_players[rj], top_score):
                adj[i].append(j)
                adj[j].append(i)
                is_canon = canonical_partner.get(ri) == rj
                weight[(i, j)] = real_edge_weight(active_players[ri], active_players[rj], top_score, is_canon)

    if has_bye_node:
        eligible = [r for r in ranks if not active_players[r].had_bye_or_equivalent]  # C2
        candidates = eligible or ranks  # entartet: alle hatten schon ein Freilos
        for r in candidates:
            i = index_of[r]
            adj[i].append(bye_node_index)
            adj[bye_node_index].append(i)
            weight[(i, bye_node_index) if i < bye_node_index else (bye_node_index, i)] = bye_edge_weight(active_players[r])

    mate = max_weight_perfect_matching(n_nodes, adj, weight)

    bye_rank: int | None = None
    pairings: list[Pairing] = []
    float_direction: dict[int, str] = {}
    seen: set[int] = set()

    for i, j in mate.items():
        if i in seen:
            continue
        seen.add(i)
        seen.add(j)
        if has_bye_node and bye_node_index in (i, j):
            player_index = j if i == bye_node_index else i
            bye_rank = ranks[player_index]
            continue
        ra, rb = ranks[i], ranks[j]
        pa, pb = active_players[ra], active_players[rb]
        pairings.append(allocate(pa, pb))
        if pa.score != pb.score:
            downfloater, upfloater = (ra, rb) if pa.score > pb.score else (rb, ra)
            float_direction[downfloater] = DOWN
            float_direction[upfloater] = UP

    return RoundResult(round_no=round_no, pairings=tuple(pairings), bye=bye_rank, float_directions=float_direction)


def apply_round(players: dict[int, Player], result: RoundResult, white_wins: dict[int, bool] | None = None) -> dict[int, Player]:
    """Baut den nächsten Turnierstand: Spielergebnisse und Float-Historie eingetragen.

    `white_wins`: {white_rank: True/False/None} je Paarung - True = Weiss gewinnt, False = Schwarz
    gewinnt, None/fehlend = Remis (0.5/0.5)."""
    new_players = dict(players)
    white_wins = white_wins or {}

    for p in result.pairings:
        white, black = players[p.white], players[p.black]
        outcome = white_wins.get(p.white)
        white_score, black_score = (1.0, 0.0) if outcome is True else (0.0, 1.0) if outcome is False else (0.5, 0.5)
        white_game = GameRecord(result.round_no, p.black, "w", white_score, counted_as_bye=False)
        black_game = GameRecord(result.round_no, p.white, "b", black_score, counted_as_bye=False)
        new_players[p.white] = _with_game(white, white_game, result.float_directions.get(p.white))
        new_players[p.black] = _with_game(black, black_game, result.float_directions.get(p.black))

    if result.bye is not None:
        bp = players[result.bye]
        bye_game = GameRecord(result.round_no, BYE, None, 1.0, counted_as_bye=True)
        new_players[result.bye] = _with_game(bp, bye_game, result.float_directions.get(result.bye))

    return new_players


def _with_game(player: Player, game: GameRecord, float_dir: str | None) -> Player:
    return Player(
        rank=player.rank,
        score=player.score + game.score,
        games=player.games + (game,),
        float_history=player.float_history + (float_dir,),
    )
