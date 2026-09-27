"""Turnierfeld generieren (Elo-Ratings, absteigend zu Startranglisten-Nummern 1..n) und eine
komplette Rundenfolge simulieren (Elo-Erwartungswert je Partie als Gewinnwahrscheinlichkeit -
Arpad Elo/USCF/FIDE-Standard, dieselbe Formel wie in `bracket-seeding-demo`)."""

from __future__ import annotations

import random
from dataclasses import dataclass

from ss_blossom import NoValidPairingError
from ss_engine import apply_round, pair_round
from ss_model import Player

BASE_RATING = 2000.0
RATING_SPREAD = 150.0


def expected_score(rating_a: float, rating_b: float) -> float:
    return 1.0 / (1.0 + 10 ** ((rating_b - rating_a) / 400.0))


@dataclass(frozen=True)
class TournamentState:
    players: dict[int, Player]
    ratings: dict[int, float]
    rounds: tuple  # tuple[RoundResult, ...] - tatsächlich gespielte Runden (kann < n_rounds sein)


def generate_tournament(n_players: int, n_rounds: int, seed: int) -> TournamentState:
    rng = random.Random(seed)
    raw_ratings = sorted((BASE_RATING + rng.gauss(0.0, RATING_SPREAD) for _ in range(n_players)), reverse=True)
    ratings = {rank: raw_ratings[rank - 1] for rank in range(1, n_players + 1)}

    players = {r: Player(rank=r) for r in range(1, n_players + 1)}
    rounds = []
    for rnd in range(1, n_rounds + 1):
        try:
            result = pair_round(players, rnd)
        except NoValidPairingError:
            break
        white_wins = {}
        for p in result.pairings:
            p_white_wins = expected_score(ratings[p.white], ratings[p.black])
            white_wins[p.white] = rng.random() < p_white_wins
        players = apply_round(players, result, white_wins)
        rounds.append(result)

    return TournamentState(players=players, ratings=ratings, rounds=tuple(rounds))
