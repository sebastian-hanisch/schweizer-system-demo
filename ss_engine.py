"""Orchestrierung: eine Runde wird nach dem FIDE-Regeltext gelöst - Brackets von oben nach unten (Score
absteigend, Art. 1.9.2), Paarungen nach Art. 3+4 - NICHT als ein globales gewichtetes Matching über die ganze
Runde (das tut der bbpPairings-treue Modus in `ss_matching_engine.py`).

Die Rundenlösung selbst steht in `ss_chain.py`, in zwei Phasen: erst die Kette der Downfloater-Mengen nach
[C5]-[C9] (billig, ohne Farben und Paarungen), dann je Block die Paarung aus dem Kandidatenstrom von
`ss_bracket.solve_bracket` (Art. 3+4, sortiert nach C10-C21). Hier bleiben das Vorbereiten der aktiven
Spieler, der letzte Rettungsanker (`_global_matching_fallback`) und das Zuteilen der Farben (Art. 5.2)."""

from __future__ import annotations

from ss_blossom import maximum_cardinality_matching
from ss_bracket import NoValidPairingError
from ss_chain import solve_round
from ss_colour import allocate
from ss_compat import compatible, topscorer_threshold_for_round
from ss_model import BYE, DOWN, GameRecord, Pairing, Player, RoundResult, UP

__all__ = ["pair_round", "apply_round", "NoValidPairingError"]

def _scoregroups(active_players: dict[int, Player]) -> list[tuple[float, list[int]]]:
    by_score: dict[float, list[int]] = {}
    for r, p in active_players.items():
        by_score.setdefault(p.score, []).append(r)
    for group in by_score.values():
        group.sort()
    return sorted(by_score.items(), key=lambda kv: -kv[0])


def _global_matching_fallback(
    active_players: dict[int, Player], topscorer_threshold: float
) -> tuple[list[tuple[int, int]], int | None] | None:
    """Letzter Rettungsanker auf Rundenebene: falls die Rundenlösung in `ss_chain.solve_round` keine Lösung
    findet, ABER irgendeine global [C1]-[C3]-konforme Paarung (ohne Rücksicht auf Bracket-Struktur oder
    Qualitätskriterien C6-C21) existiert, wird DIE verwendet, statt fälschlich [C4]/Art. 1.9.3 zu melden. Bewusster Kompromiss: Korrektheit (eine
    Paarung existiert überhaupt) hat Vorrang vor FIDE-Qualitätsoptimalität in diesem Randfall."""
    ranks = sorted(active_players)
    n_real = len(ranks)
    has_bye_node = n_real % 2 == 1
    n_nodes = n_real + (1 if has_bye_node else 0)
    adj: list[list[int]] = [[] for _ in range(n_nodes)]
    for i in range(n_real):
        for j in range(i + 1, n_real):
            if compatible(active_players[ranks[i]], active_players[ranks[j]], topscorer_threshold):
                adj[i].append(j)
                adj[j].append(i)
    if has_bye_node:
        bye_idx = n_real
        for i, r in enumerate(ranks):
            if not active_players[r].had_bye_or_equivalent:
                adj[i].append(bye_idx)
                adj[bye_idx].append(i)

    mate = maximum_cardinality_matching(n_nodes, adj)
    if len(mate) != n_nodes:
        return None

    pairs: list[tuple[int, int]] = []
    bye_rank: int | None = None
    seen: set[int] = set()
    for i, j in mate.items():
        if i in seen:
            continue
        seen.add(i)
        seen.add(j)
        if has_bye_node and n_real in (i, j):
            bye_rank = ranks[j if i == n_real else i]
            continue
        pairs.append((ranks[i], ranks[j]))
    return pairs, bye_rank


def pair_round(
    players: dict[int, Player], round_no: int, absent: frozenset[int] = frozenset(), total_rounds: int | None = None
) -> RoundResult:
    """`absent`: Spieler, die für DIESE Runde vorab abgemeldet sind (TRF-Freilos-Anfrage, z. B.
    Code "Z" = Null-Punkte-Freilos auf eigenen Wunsch) - bleiben im Turnier, werden aber in dieser
    Runde nicht gepaart. `total_rounds`: die geplante GESAMT-Rundenzahl des Turniers - Art. 1.8
    definiert "Spitzenreiter" als "Score > 50 % der maximal MÖGLICHEN Punktzahl" (nicht: gleich dem
    aktuellen Höchststand!), was die Gesamtrundenzahl voraussetzt. Ohne Angabe (z. B. in Tests ohne
    festgelegte Gesamtrundenzahl) wird ersatzweise die Anzahl BEREITS gespielter Runden verwendet
    (`round_no - 1`) - das reproduziert das beobachtete Verhalten von bbpPairings, wenn die
    Gesamtrundenzahl selbst nicht bekannt ist. Wirft `NoValidPairingError` (Art. 1.9.3), wenn keine
    C1-C4-konforme Paarung existiert - ein echter, in der FIDE-Praxis vorkommender Turnierleiter-Fall."""
    active_players = {r: p for r, p in players.items() if r not in absent}
    topscorer_threshold = topscorer_threshold_for_round(round_no, total_rounds)
    groups = _scoregroups(active_players)

    result = solve_round(groups, active_players, topscorer_threshold)
    if result is None:
        result = _global_matching_fallback(active_players, topscorer_threshold)
    if result is None:
        raise NoValidPairingError("keine gültige Rundenpaarung gefunden (Art. 1.9.3)")
    raw_pairs, bye_rank = result

    pairings: list[Pairing] = []
    float_direction: dict[int, str] = {}
    for a, b in raw_pairs:
        pa, pb = active_players[a], active_players[b]
        pairings.append(allocate(pa, pb))
        if pa.score != pb.score:
            downfloater, upfloater = (a, b) if pa.score > pb.score else (b, a)
            float_direction[downfloater] = DOWN
            float_direction[upfloater] = UP
    if bye_rank is not None:
        float_direction[bye_rank] = DOWN  # Art. 1.4.3: PAB-Empfänger bekommt einen Downfloat

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
