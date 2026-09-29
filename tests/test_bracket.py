"""Gezielte Tests für `ss_bracket.py`s Kandidatensuche, ergänzend zu den Ende-zu-Ende-Tests in
`test_engine.py`/`test_oracle_bbppairings.py`."""

from __future__ import annotations

from ss_bracket import BracketContext, solve_bracket
from ss_model import GameRecord, Player


def test_multiple_competing_mdps_prefer_lower_scored_one_to_cascade_further():
    # Regressionstest (echter, gegen bbpPairings.exe gefundener Bug, siehe
    # project_turnierplanung_dag_scoping.md, achte Architekturrunde): zwei hereingefloatete MDPs
    # (3, 8) konkurrieren um den EINEN freien Residenten (5) dieser Bracket - `_exchange_cost`
    # deckt diesen Fall nicht ab (das vergleicht nur MDP-zu-Residenten-Paare gegen eine volle
    # Baseline-Paarung, nicht "welcher von mehreren MDPs bleibt unversorgt"). Der niedriger
    # bewertete MDP soll weiter kaskadieren (der höher bewertete bleibt eher versorgt) - hier mit
    # identischem Score, also entscheidet die Art.-1.2-Rangfolge: der SPÄTER gereihte (Rang 8)
    # kaskadiert, der FRÜHER gereihte (Rang 3) bleibt.
    players = {
        3: Player(rank=3, score=2.0),
        5: Player(rank=5, score=1.0),
        8: Player(rank=8, score=2.0),
    }
    ctx = BracketContext(players=players, topscorer_threshold=99.0)
    best = next(iter(solve_bracket([5], [3, 8], ctx)))
    assert best.pairs == ((3, 5),)
    assert best.downfloaters == (8,)


def test_multiple_competing_mdps_lower_score_one_cascades_even_if_earlier_ranked():
    # Wie oben, aber mit UNTERSCHIEDLICHEN Scores: MDP 8 hat den niedrigeren Score (1.5 statt 2.0)
    # - er soll kaskadieren, auch wenn er (hier bewusst) den FRÜHEREN Rang hat.
    players = {
        8: Player(rank=8, score=1.5),
        5: Player(rank=5, score=1.0),
        30: Player(rank=30, score=2.0),
    }
    ctx = BracketContext(players=players, topscorer_threshold=99.0)
    best = next(iter(solve_bracket([5], [8, 30], ctx)))
    assert best.pairs == ((30, 5),)
    assert best.downfloaters == (8,)


def test_downfloater_choice_prefers_one_that_can_still_reach_next_bracket():
    # Regressionstest (echter, gegen bbpPairings.exe gefundener Bug, siehe
    # project_turnierplanung_dag_scoping.md, achte Architekturrunde, zweiter Fund): in einer
    # homogenen Bracket {5,6,7} (Score 2.0, ungerade) sind ALLE drei Paarungen gleich gut bewertet
    # (kein MDP beteiligt, `_mdp_downfloat_bias` greift hier nicht) - `_exchange_cost` und die
    # reine Generierungsreihenfolge unterscheiden hier NICHT zuverlässig. bbpPairings bevorzugt
    # (empirisch bestätigt an einem echten Mismatch-Fall), dass der Downfloater derjenige ist, der
    # noch mindestens einen kompatiblen Partner in der UNMITTELBAR NÄCHSTEN Bracket hat (hier: 10) -
    # NICHT der, der diese Bracket komplett überspringen müsste. Hier hat 6 bereits gegen 10
    # gespielt (kann 10 nicht mehr erreichen), 7 nicht - 7 soll deshalb downfloaten, nicht 6.
    players = {
        5: Player(rank=5, score=2.0),
        6: Player(rank=6, score=2.0, games=(GameRecord(1, 10, "w", 1.0, counted_as_bye=False),)),
        7: Player(rank=7, score=2.0),
        10: Player(rank=10, score=1.0),
    }
    ctx = BracketContext(players=players, topscorer_threshold=99.0)
    best = next(iter(solve_bracket([5, 6, 7], [], ctx, (10,))))
    assert best.pairs == ((5, 6),)
    assert best.downfloaters == (7,)


def test_downfloater_choice_is_not_a_positional_shortcut():
    # Regressionstest gegen genau die Klasse von Fix, die in derselben Sitzung ZWEIMAL gemessen
    # katastrophal scheiterte (76,6 %/77,2 % statt ~99,5 % - siehe project_turnierplanung_dag_
    # scoping.md, neunte Architekturrunde): ein pauschaler "spätester Rang downfloatet"-Kurzschluss
    # statt echter `compatible()`-Prüfung gegen `next_group_residents`. Der vorherige Test hätte
    # eine solche Regression NICHT gefangen - dort ist der spätest gereihte Resident (7) zufällig
    # auch derjenige, der die nächste Bracket noch erreichen kann, sodass ein reiner
    # Rang-Kurzschluss dieselbe (korrekte) Antwort liefern würde. Hier ist es umgekehrt: der
    # spätest gereihte Resident (7) hat BEREITS gegen 10 gespielt (kann die nächste Bracket NICHT
    # mehr erreichen) - ein Rang-Kurzschluss würde trotzdem 7 downfloaten lassen (FALSCH); die
    # echte Kompatibilitätsprüfung muss stattdessen 6 wählen (kann 10 noch erreichen), NICHT 7.
    players = {
        5: Player(rank=5, score=2.0),
        6: Player(rank=6, score=2.0),
        7: Player(rank=7, score=2.0, games=(GameRecord(1, 10, "w", 1.0, counted_as_bye=False),)),
        10: Player(rank=10, score=1.0),
    }
    ctx = BracketContext(players=players, topscorer_threshold=99.0)
    best = next(iter(solve_bracket([5, 6, 7], [], ctx, (10,))))
    assert 7 not in best.downfloaters
