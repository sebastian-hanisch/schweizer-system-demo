"""Datenmodell: Spieler, Partien, Paarungen, Rundenergebnis - unveränderliche Dataclasses.

Ein "Spieler" hier ist immer seine Startrangliste-Nummer (1..n), die über das ganze Turnier fest
bleibt - genau wie die TRF-Spielernummer, mit der `ss_oracle_bbppairings.py` abgleicht.
"""

from __future__ import annotations

from dataclasses import dataclass, field

BYE = 0  # Spielernummer 0 = Freilos-Gegner, wie in TRF-Dateien üblich (bbpPairings-Konvention)

WHITE, BLACK = "w", "b"


@dataclass(frozen=True)
class GameRecord:
    round_no: int
    opponent: int  # BYE (0), falls Freilos
    colour: str | None  # None bei Freilos
    score: float  # Punkte aus dieser Runde (1.0 Sieg, 0.5 Remis, 0.0 Niederlage/nicht gespielt)
    counted_as_bye: bool  # True bei Freilos ODER "so viele Punkte wie ein Sieg ohne zu spielen" (C2)


DOWN, UP = "down", "up"  # Float-Richtung je Runde: "down" = Downfloater (aus der eigenen Bracket gefallen),
# "up" = MDP-Gegner (Resident, der gegen einen hereingefloateten Spieler höherer/tieferer Bracket spielte).
# None = kein Float in dieser Runde. Getrennt von GameRecord gespeichert, weil die Float-Richtung eine
# Eigenschaft der PAARUNGSENTSCHEIDUNG ist (Art. 1.4), nicht aus dem Spielergebnis ableitbar.


@dataclass(frozen=True)
class Player:
    rank: int  # Startranglisten-Nummer, 1..n, fest über das ganze Turnier
    score: float = 0.0
    games: tuple[GameRecord, ...] = field(default_factory=tuple)
    float_history: tuple[str | None, ...] = field(default_factory=tuple)  # je Runde: DOWN, UP oder None

    @property
    def opponents(self) -> frozenset[int]:
        return frozenset(g.opponent for g in self.games if g.opponent != BYE)

    @property
    def had_bye_or_equivalent(self) -> bool:
        return any(g.counted_as_bye for g in self.games)

    @property
    def unplayed_games(self) -> int:
        return sum(1 for g in self.games if g.opponent == BYE)

    @property
    def colour_difference(self) -> int:
        """Weiß-Partien minus Schwarz-Partien (bei echten Partien, Freilose zählen nicht)."""
        diff = 0
        for g in self.games:
            if g.colour == WHITE:
                diff += 1
            elif g.colour == BLACK:
                diff -= 1
        return diff

    @property
    def last_two_colours(self) -> tuple[str, ...]:
        played = [g.colour for g in self.games if g.colour is not None]
        return tuple(played[-2:])

    @property
    def last_colour(self) -> str | None:
        played = [g.colour for g in self.games if g.colour is not None]
        return played[-1] if played else None

    def float_in_last_n_rounds(self, n: int) -> tuple[str | None, ...]:
        """Float-Richtung der letzten n gespielten Runden, jüngste zuerst (für C14-C21)."""
        return tuple(reversed(self.float_history[-n:]))


@dataclass(frozen=True)
class Pairing:
    white: int
    black: int


@dataclass(frozen=True)
class RoundResult:
    round_no: int
    pairings: tuple[Pairing, ...]
    bye: int | None  # Spielerrang, der ein Freilos bekommt (oder None bei gerader Teilnehmerzahl)
    float_directions: dict = field(default_factory=dict)  # Rang -> DOWN/UP, nur wer in dieser Runde floatete
