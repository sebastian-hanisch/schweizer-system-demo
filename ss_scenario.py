"""Turnierfeld generieren (Elo-Ratings, absteigend zu Startranglisten-Nummern 1..n) und eine
komplette Rundenfolge simulieren (Elo-Erwartungswert je Partie als Gewinnwahrscheinlichkeit -
Arpad Elo/USCF/FIDE-Standard, dieselbe Formel wie in `bracket-seeding-demo`)."""

from __future__ import annotations

import random
from dataclasses import dataclass

import ss_engine
import ss_matching_engine
from ss_engine import apply_round
from ss_model import Player

# Beide Engines haben je ihre EIGENE `NoValidPairingError` (bewusst unabhängig, keine Kopplung
# zwischen den Modulen - siehe `ss_matching_engine.py`s Moduldoku) - `generate_tournament` muss BEIDE
# abfangen können, unabhängig vom gewählten Modus.
_NO_VALID_PAIRING_ERRORS = (ss_engine.NoValidPairingError, ss_matching_engine.NoValidPairingError)

RULESET, MATCHING = "ruleset", "matching"

BASE_RATING = 2000.0
RATING_SPREAD = 150.0


def expected_score(rating_a: float, rating_b: float) -> float:
    return 1.0 / (1.0 + 10 ** ((rating_b - rating_a) / 400.0))


@dataclass(frozen=True)
class TournamentState:
    players: dict[int, Player]
    ratings: dict[int, float]
    rounds: tuple  # tuple[RoundResult, ...] - tatsächlich gespielte Runden (kann < n_rounds sein)


def generate_tournament(n_players: int, n_rounds: int, seed: int, engine_mode: str = RULESET) -> TournamentState:
    """`engine_mode`: `RULESET` (Standard, `ss_engine.pair_round` - wörtlich am FIDE-Regeltext Art. 3+4,
    Schritt für Schritt nachvollziehbar) oder `MATCHING` (`ss_matching_engine.pair_round_matching` -
    bbpPairings' EIGENER Mechanismus, ein einziges rundenweit fortgeführtes Matching-Objekt, exakt aber
    nicht in Einzelschritte zerlegbar - siehe dessen Moduldoku)."""
    pair_fn = ss_engine.pair_round if engine_mode == RULESET else ss_matching_engine.pair_round_matching

    rng = random.Random(seed)
    raw_ratings = sorted((BASE_RATING + rng.gauss(0.0, RATING_SPREAD) for _ in range(n_players)), reverse=True)
    ratings = {rank: raw_ratings[rank - 1] for rank in range(1, n_players + 1)}

    players = {r: Player(rank=r) for r in range(1, n_players + 1)}
    rounds = []
    for rnd in range(1, n_rounds + 1):
        try:
            result = pair_fn(players, rnd, total_rounds=n_rounds)
        except _NO_VALID_PAIRING_ERRORS:
            break
        white_wins = {}
        for p in result.pairings:
            p_white_wins = expected_score(ratings[p.white], ratings[p.black])
            white_wins[p.white] = rng.random() < p_white_wins
        players = apply_round(players, result, white_wins)
        rounds.append(result)

    return TournamentState(players=players, ratings=ratings, rounds=tuple(rounds))
