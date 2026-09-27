"""Turniertabelle und Kennzahlen aus einem simulierten Turnierstand."""

from __future__ import annotations

from dataclasses import dataclass

from ss_model import Player


@dataclass(frozen=True)
class StandingsRow:
    rank: int
    rating: float
    score: float
    white_games: int
    black_games: int
    byes: int


def standings(players: dict[int, Player], ratings: dict[int, float]) -> list[StandingsRow]:
    rows = []
    for r in players:
        p = players[r]
        white = sum(1 for g in p.games if g.colour == "w")
        black = sum(1 for g in p.games if g.colour == "b")
        byes = sum(1 for g in p.games if g.counted_as_bye)
        rows.append(StandingsRow(rank=r, rating=ratings[r], score=p.score, white_games=white, black_games=black, byes=byes))
    rows.sort(key=lambda row: (-row.score, row.rank))
    return rows


def max_colour_imbalance(players: dict[int, Player]) -> int:
    return max((abs(p.colour_difference) for p in players.values()), default=0)


def total_byes(rounds) -> int:
    return sum(1 for r in rounds if r.bye is not None)
