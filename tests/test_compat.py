"""C1/C3-Kompatibilitätsprüfung - insbesondere die [C3]-Spitzenreiter-Ausnahme (Art. 2.1.3), zwei
echte, gegen bbpPairings.exe gefundene Regressionen."""

from __future__ import annotations

from ss_compat import compatible
from ss_model import GameRecord, Player


def _absolute_black(rank: int, score: float) -> Player:
    # zwei Weiss-Partien in Folge -> absolute Schwarz-Präferenz (Art. 1.7.1)
    games = (
        GameRecord(1, 90 + rank, "w", 1.0, counted_as_bye=False),
        GameRecord(2, 91 + rank, "w", 1.0, counted_as_bye=False),
    )
    return Player(rank=rank, score=score, games=games)


def test_c1_blocks_rematch_regardless_of_score():
    a = Player(rank=1, score=1.0, games=(GameRecord(1, 2, "w", 1.0, counted_as_bye=False),))
    b = Player(rank=2, score=0.0, games=(GameRecord(1, 1, "b", 0.0, counted_as_bye=False),))
    assert compatible(a, b, topscorer_threshold=0.0) is False


def test_c3_blocks_two_non_topscorers_with_same_absolute_preference():
    a = _absolute_black(1, score=2.0)
    b = _absolute_black(2, score=2.0)
    # topscorer_threshold = 3.0 (z. B. 6 Runden gesamt) -> beide (Score 2.0) sind NICHT Spitzenreiter
    assert compatible(a, b, topscorer_threshold=3.0) is False


def test_c3_allows_meeting_when_only_one_is_topscorer():
    # Regressionstest (echter, gegen bbpPairings.exe gefundener Bug): die Einschränkung gilt nur
    # für ZWEI Nicht-Spitzenreiter (Art. 2.1.3) - ist EINER der beiden Spitzenreiter (Score >
    # topscorer_threshold), greift C3 gar nicht erst. Die vorherige Fassung verlangte fälschlich,
    # dass BEIDE Spitzenreiter sind.
    topscorer = _absolute_black(1, score=4.0)  # > threshold -> Spitzenreiter
    non_topscorer = _absolute_black(2, score=2.0)  # <= threshold -> kein Spitzenreiter
    assert compatible(topscorer, non_topscorer, topscorer_threshold=3.0) is True


def test_c3_topscorer_threshold_is_half_of_maximum_possible_not_current_leader():
    # Regressionstest (echter, gegen bbpPairings.exe gefundener Bug): Art. 1.8 definiert
    # "Spitzenreiter" als Score > 50 % der maximal MÖGLICHEN Punktzahl (hier: 6 Runden gesamt ->
    # Schwelle 3.0) - NICHT als Gleichstand mit dem aktuell höchsten Score im Feld. Ein Spieler mit
    # Score 3.0 ist noch KEIN Spitzenreiter (3.0 ist nicht > 3.0), selbst wenn er aktuell führt.
    leader_not_yet_topscorer = _absolute_black(1, score=3.0)
    other = _absolute_black(2, score=2.0)
    assert compatible(leader_not_yet_topscorer, other, topscorer_threshold=3.0) is False
    clear_topscorer = _absolute_black(1, score=3.5)
    assert compatible(clear_topscorer, other, topscorer_threshold=3.0) is True
