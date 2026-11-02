"""Baku-Beschleunigung (FIDE C.04.7, Abschnitt 1) als Aufsatz auf beide Paarungs-Engines.

Regel: Vor der ersten Runde wird die Startrangliste in GA (die obere Hälfte, aufgerundet auf eine
GERADE Zahl: 2 * ceil(N / 4)) und GB (der Rest) geteilt. "Beschleunigte Runden" sind die ersten
ceil(R / 2) Runden. GA bekommt vor der ersten Hälfte (aufgerundet) davon einen virtuellen Punkt (so
viel wie ein Sieg zählt), vor den übrigen beschleunigten Runden einen halben, danach nichts mehr.
Der Paarungs-Score ist Tabellenpunkte + virtuelle Punkte (Art. 1.5).

Warum KEINE Änderung an den Engines nötig ist: bbpPairings (die Referenz) rechnet in `dutch.cpp`
an jeder Stelle mit `scoreWithAcceleration` - Score-Gruppen, Freilos-Wahl [C5], Farbvergleich
(Art. 5.2.4) und die Float-Historie der Vorrunden; selbst die Topscorer-Grenze (die ohnehin nur in
der letzten Runde greift, in der es bei mindestens 2 Runden nie eine Beschleunigung gibt) vergleicht
`scoreWithAcceleration`. Es genügt deshalb, den Engines Spieler zu geben, deren `score` schon der
Paarungs-Score ist. Die Tabellenpunkte bleiben im echten Turnierstand unberührt, `apply_round`
rechnet auf diesem, nicht auf der Sicht.

Nicht abgebildet: Nachmeldungen (Art. 1.3) - die Demo hat ein festes Feld.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import replace

from ss_model import Player, RoundResult

POINTS_FOR_WIN = 1.0  # Demo-Wertung: Sieg 1, Remis 0,5 (Art. 1.1 verlangt Sieg = 2 Remis)


def group_a_size(n_players: int) -> int:
    """Art. 1.2: obere Hälfte, aufgerundet auf die nächste GERADE Zahl = 2 * ceil(N / 4)."""
    return 2 * -(-n_players // 4)


def accelerated_rounds(total_rounds: int) -> int:
    """Art. 1.4.1: die ersten ceil(R / 2) Runden."""
    return -(-total_rounds // 2)


def virtual_points(total_rounds: int, round_no: int) -> float:
    """Virtuelle Punkte, die GA vor Runde `round_no` bekommt (Art. 1.4.2/1.4.3)."""
    accelerated = accelerated_rounds(total_rounds)
    full = -(-accelerated // 2)
    if round_no <= full:
        return POINTS_FOR_WIN
    if round_no <= accelerated:
        return POINTS_FOR_WIN / 2
    return 0.0


def virtual_points_by_rank(n_players: int, total_rounds: int, round_no: int) -> dict[int, float]:
    """Rang -> virtuelle Punkte vor dieser Runde (nur GA-Spieler, nur wenn > 0)."""
    points = virtual_points(total_rounds, round_no)
    if points == 0.0:
        return {}
    return {rank: points for rank in range(1, group_a_size(n_players) + 1) if rank <= n_players}


def with_pairing_scores(players: dict[int, Player], virtual: dict[int, float]) -> dict[int, Player]:
    """Sicht für die Paarung: `score` = Tabellenpunkte + virtuelle Punkte (Art. 1.5)."""
    return {r: replace(p, score=p.score + virtual[r]) if virtual.get(r) else p for r, p in players.items()}


def accelerations_by_rank(n_players: int, total_rounds: int) -> dict[int, list[float]]:
    """Rang -> virtuelle Punkte je Runde 1..R (nur GA) - dieselben Werte, die das Orakel als
    `XXA`-Zeilen bekommt."""
    return {
        rank: [virtual_points(total_rounds, rnd) for rnd in range(1, total_rounds + 1)]
        for rank in range(1, min(group_a_size(n_players), n_players) + 1)
    }


def pair_round_accelerated(
    pair_fn: Callable[..., RoundResult], players: dict[int, Player], round_no: int, total_rounds: int, **kwargs
) -> RoundResult:
    """Paart eine Runde mit Baku-Beschleunigung. `pair_fn` ist `ss_engine.pair_round` oder
    `ss_matching_engine.pair_round_matching`. Das Ergebnis (Paarungen, Freilos, Float-Richtungen)
    gilt für die ECHTEN Spieler weiter."""
    virtual = virtual_points_by_rank(len(players), total_rounds, round_no)
    return pair_fn(with_pairing_scores(players, virtual), round_no, total_rounds=total_rounds, **kwargs)
