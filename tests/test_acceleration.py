"""Baku-Beschleunigung (FIDE C.04.7, Abschnitt 1): die Regel von Hand, Eigenschaften der beschleunigten
Turniere, und - nur mit `BBPPAIRINGS_EXE` - der Abgleich mit bbpPairings über `XXA`-Zeilen.

Literatur-Schicht: die zwei Beispiele aus 1.4.4 des Regeltexts (9-Runden-Einzelturnier: 1, 1, 1, 0,5, 0,5;
11-Runden-Mannschaftsturnier: je 3 Runden voll und halb) und die Gruppengröße 82 bei 161 Teilnehmern aus
1.2. Eigenschafts-Schicht: Runde 1 mischt GA und GB nie; die echten Punkte bleiben unverfälscht.
"""

import os
import random

import pytest

import ss_acceleration as acc
import ss_engine
import ss_matching_engine
from ss_model import Player
from ss_oracle_bbppairings import _acceleration_line, run_bbppairings
from ss_scenario import MATCHING, RULESET, generate_tournament

EXE_PATH = os.environ.get("BBPPAIRINGS_EXE")
needs_oracle = pytest.mark.skipif(not EXE_PATH, reason="BBPPAIRINGS_EXE nicht gesetzt - Oracle-Tests übersprungen")

ENGINES = {RULESET: ss_engine.pair_round, MATCHING: ss_matching_engine.pair_round_matching}


# --- Regel von Hand (Literatur) ---------------------------------------------------------------


def test_group_a_size_matches_regeltext_example():
    # Art. 1.2, Anmerkung: 161 Teilnehmer -> Hälfte 80,5 -> nächste gerade Zahl 82 = 2 * ceil(161 / 4).
    assert acc.group_a_size(161) == 82


@pytest.mark.parametrize("n, expected", [(4, 2), (5, 4), (8, 4), (9, 6), (10, 6), (16, 8), (32, 16), (1, 2)])
def test_group_a_size_is_even_upper_half(n, expected):
    assert acc.group_a_size(n) == expected
    assert acc.group_a_size(n) % 2 == 0


@pytest.mark.parametrize("rounds, expected", [(1, 1), (2, 1), (3, 2), (9, 5), (11, 6)])
def test_accelerated_rounds_is_first_half_rounded_up(rounds, expected):
    assert acc.accelerated_rounds(rounds) == expected


def test_virtual_points_nine_round_individual_tournament():
    # Art. 1.4.4, Beispiel 1: fünf beschleunigte Runden, ein virtueller Punkt in den ersten drei,
    # ein halber in den nächsten zwei, danach nichts.
    assert [acc.virtual_points(9, r) for r in range(1, 10)] == [1.0, 1.0, 1.0, 0.5, 0.5, 0.0, 0.0, 0.0, 0.0]


def test_virtual_points_eleven_round_event_halves_after_three_rounds():
    # Art. 1.4.4, Beispiel 2: sechs beschleunigte Runden, je drei voll und drei halb (hier mit dem
    # Punktwert 1 statt 2 Matchpunkten, also 1 und 0,5).
    assert [acc.virtual_points(11, r) for r in range(1, 12)] == [1.0] * 3 + [0.5] * 3 + [0.0] * 5


def test_virtual_points_by_rank_only_group_a_and_only_while_accelerated():
    first = acc.virtual_points_by_rank(10, 9, 1)
    assert first == {rank: 1.0 for rank in range(1, 7)}  # GA = 6 von 10
    assert acc.virtual_points_by_rank(10, 9, 6) == {}  # nach der letzten beschleunigten Runde nichts mehr


def test_accelerations_by_rank_lists_all_rounds_for_group_a_only():
    table = acc.accelerations_by_rank(8, 9)
    assert set(table) == {1, 2, 3, 4}
    assert table[1] == [1.0, 1.0, 1.0, 0.5, 0.5, 0.0, 0.0, 0.0, 0.0]


def test_pairing_view_adds_virtual_points_without_touching_real_players():
    players = {r: Player(rank=r, score=1.0 if r == 1 else 0.0) for r in range(1, 5)}
    view = acc.with_pairing_scores(players, {1: 1.0, 2: 1.0})
    assert [view[r].score for r in range(1, 5)] == [2.0, 1.0, 0.0, 0.0]
    assert [players[r].score for r in range(1, 5)] == [1.0, 0.0, 0.0, 0.0]


@pytest.mark.parametrize("mode", [RULESET, MATCHING])
def test_round_one_pairs_inside_each_group_by_hand(mode):
    # Von Hand: 8 Spieler, 9 Runden -> GA = 1-4, GB = 5-8. Beide Gruppen sind homogene Brackets
    # (jeweils 4 Spieler): obere Hälfte gegen untere Hälfte, also 1-3 und 2-4 bzw. 5-7 und 6-8
    # (ohne Beschleunigung wäre es 1-5, 2-6, 3-7, 4-8).
    players = {r: Player(rank=r) for r in range(1, 9)}
    result = acc.pair_round_accelerated(ENGINES[mode], players, 1, 9)
    assert {frozenset((p.white, p.black)) for p in result.pairings} == {
        frozenset((1, 3)), frozenset((2, 4)), frozenset((5, 7)), frozenset((6, 8)),
    }
    plain = ENGINES[mode](players, 1, total_rounds=9)
    assert {frozenset((p.white, p.black)) for p in plain.pairings} == {
        frozenset((1, 5)), frozenset((2, 6)), frozenset((3, 7)), frozenset((4, 8)),
    }


# --- Eigenschaften ----------------------------------------------------------------------------


@pytest.mark.parametrize("mode", [RULESET, MATCHING])
def test_round_one_never_mixes_group_a_and_group_b(mode):
    for n in range(4, 33):
        players = {r: Player(rank=r) for r in range(1, n + 1)}
        result = acc.pair_round_accelerated(ENGINES[mode], players, 1, 9)
        size = acc.group_a_size(n)
        for p in result.pairings:
            assert (p.white <= size) == (p.black <= size), f"n={n}: {p.white}-{p.black} mischt GA und GB"


@pytest.mark.parametrize("mode", [RULESET, MATCHING])
def test_accelerated_tournament_keeps_absolute_criteria_and_real_scores(mode):
    for n, rounds, seed in [(12, 5, 1), (13, 7, 2), (16, 9, 3), (21, 6, 4)]:
        t = generate_tournament(n, rounds, seed, engine_mode=mode, accelerated=True)
        assert t.accelerated
        seen = set()
        byes = []
        for r in t.rounds:
            for p in r.pairings:
                pair = frozenset((p.white, p.black))
                assert pair not in seen, f"n={n}: {pair} spielt zweimal (C1)"
                seen.add(pair)
            if r.bye is not None:
                byes.append(r.bye)
        assert len(byes) == len(set(byes)), f"n={n}: zweites Freilos (C2)"
        # Echte Punkte: jede gespielte Partie verteilt genau 1 Punkt, jedes Freilos 1 Punkt - keine virtuellen.
        games = sum(len(r.pairings) for r in t.rounds) + len(byes)
        assert sum(p.score for p in t.players.values()) == pytest.approx(games)


def test_default_tournament_is_not_accelerated_and_unchanged_by_the_flag():
    base = generate_tournament(12, 5, 7)
    assert not base.accelerated
    assert generate_tournament(12, 5, 7, accelerated=False).rounds == base.rounds


def test_acceleration_actually_changes_the_pairings():
    plain = generate_tournament(16, 7, 5)
    fast = generate_tournament(16, 7, 5, accelerated=True)
    assert plain.rounds[0] != fast.rounds[0]


def test_acceleration_line_matches_trf_column_layout():
    # Spielernummer in Spalte 5-8, danach je Runde ein 4-stelliger Wert im 5er-Raster ab Spalte 10.
    line = _acceleration_line(3, [1.0, 1.0, 0.5])
    assert line == "XXA    3  1.0  1.0  0.5"
    assert line[4:8] == "   3" and line[9:13] == " 1.0" and line[14:18] == " 1.0" and line[19:23] == " 0.5"


# --- Abgleich mit bbpPairings -----------------------------------------------------------------


@needs_oracle
@pytest.mark.parametrize("mode", [RULESET, MATCHING])
def test_round_one_matches_bbppairings_for_several_field_sizes(mode):
    for n in (4, 5, 6, 8, 9, 12, 13, 16, 21, 32):
        players = {r: Player(rank=r) for r in range(1, n + 1)}
        mine = acc.pair_round_accelerated(ENGINES[mode], players, 1, 9)
        theirs, bye = run_bbppairings(
            players, 1, exe_path=EXE_PATH, accelerations=acc.accelerations_by_rank(n, 9), total_rounds=9
        )
        assert {frozenset((p.white, p.black)) for p in mine.pairings} == {frozenset(p) for p in theirs}, f"n={n}"
        assert mine.bye == bye, f"n={n}"


@needs_oracle
def test_oracle_really_reacts_to_the_acceleration_lines():
    # Schutz gegen einen stillen Fehler im TRF-Schreiber: ohne wirksame XXA-Zeilen wäre jeder Abgleich
    # mit der beschleunigten Engine vergleichsweise zufällig.
    players = {r: Player(rank=r) for r in range(1, 9)}
    plain, _ = run_bbppairings(players, 1, exe_path=EXE_PATH, total_rounds=9)
    fast, _ = run_bbppairings(
        players, 1, exe_path=EXE_PATH, accelerations=acc.accelerations_by_rank(8, 9), total_rounds=9
    )
    assert {frozenset(p) for p in plain} == {frozenset(p) for p in [(1, 5), (2, 6), (3, 7), (4, 8)]}
    assert {frozenset(p) for p in fast} == {frozenset(p) for p in [(1, 3), (2, 4), (5, 7), (6, 8)]}


def _agreement(mode, sizes, round_counts, seeds, accelerate=True):
    """Anteil der Runden, in denen Paarungen UND Freilos mit bbpPairings übereinstimmen. Das Turnier
    wird von der Referenz selbst fortgeführt, damit beide Seiten denselben Stand sehen (sonst
    verzerren frühere Abweichungen alle Folgerunden)."""
    from ss_model import DOWN, UP, Pairing, RoundResult

    fn = ENGINES[mode]
    total = same = 0
    wrong_colours = 0  # Runden mit gleicher Paarung, aber anderer Farbverteilung als die Referenz
    for n in sizes:
        for rounds in round_counts:
            for seed in seeds:
                rng = random.Random(seed * 1000 + n * 10 + rounds)
                players = {r: Player(rank=r) for r in range(1, n + 1)}
                accs = acc.accelerations_by_rank(n, rounds) if accelerate else None
                for rnd in range(1, rounds + 1):
                    try:
                        theirs, bye = run_bbppairings(
                            players, rnd, exe_path=EXE_PATH, accelerations=accs, total_rounds=rounds
                        )
                    except RuntimeError:
                        break  # kleines Feld erschöpft: auch die Referenz findet keine Paarung mehr
                    view = acc.with_pairing_scores(players, acc.virtual_points_by_rank(n, rounds, rnd) if accelerate else {})
                    try:
                        mine = fn(view, rnd, total_rounds=rounds)
                        ok = {frozenset((p.white, p.black)) for p in mine.pairings} == {frozenset(p) for p in theirs}
                        ok = ok and mine.bye == bye
                        if ok and {(p.white, p.black) for p in mine.pairings} != {tuple(p) for p in theirs}:
                            wrong_colours += 1
                    except (ss_engine.NoValidPairingError, ss_matching_engine.NoValidPairingError):
                        ok = False
                    total += 1
                    same += ok
                    floats = {}
                    for w, b in theirs:
                        if view[w].score != view[b].score:
                            high, low = (w, b) if view[w].score > view[b].score else (b, w)
                            floats[high], floats[low] = DOWN, UP
                    if bye is not None:
                        floats[bye] = DOWN
                    result = RoundResult(rnd, tuple(Pairing(w, b) for w, b in theirs), bye, floats)
                    outcomes = {w: rng.choice((True, False, None)) for w, _ in theirs}
                    players = ss_engine.apply_round(players, result, outcomes)
    return same / total, total, wrong_colours


@needs_oracle
def test_matching_mode_agrees_exactly_with_bbppairings_on_accelerated_tournaments():
    # Gemessen 100 % (576 von 576 Runden; 8-31 Spieler, 5-9 Runden), Paarung, Freilos UND Farben. Diese
    # Stichprobe ist eine Teilmenge davon (gleiche Saatwerte), darum ist die Prüfung exakt.
    rate, total, wrong_colours = _agreement(MATCHING, sizes=(8, 11, 14, 17), round_counts=(5, 9), seeds=range(2))
    assert total >= 60
    assert rate == 1.0, f"{rate:.1%} von {total}"
    assert wrong_colours == 0


@needs_oracle
def test_matching_mode_agrees_exactly_without_acceleration_on_larger_fields():
    # Regression der Spitzenreiter-Regel (ss_compat.topscorer_threshold_for_round): mit Grenze R/2 und
    # der C3-Ausnahme in jeder Runde stimmten hier 4 von 574 Runden nicht (99,3 %), jetzt alle.
    rate, total, wrong_colours = _agreement(
        MATCHING, sizes=(8, 11, 14, 17), round_counts=(5, 7, 9), seeds=range(4), accelerate=False
    )
    assert total >= 100
    assert rate == 1.0, f"{rate:.1%} von {total}"
    assert wrong_colours == 0


@needs_oracle
def test_ruleset_mode_agrees_with_bbppairings_on_accelerated_tournaments():
    # Gemessen 97,9 % (564 von 576) - ohne Beschleunigung 98,6 %: die Beschleunigung kostet höchstens ein paar Runden.
    # Diese Teilmenge: 100 % (79 von 79); Schwelle mit Abstand nach unten.
    rate, total, wrong_colours = _agreement(RULESET, sizes=(8, 11, 14), round_counts=(5, 9), seeds=range(2))
    assert total >= 40
    assert rate >= 0.95, f"{rate:.1%} von {total}"
    assert wrong_colours == 0


@needs_oracle
def test_ruleset_mode_agrees_with_bbppairings_on_larger_fields_without_acceleration():
    # Regression der Bracket-Suche (ss_bracket: perfekter bzw. bester Kandidat auch jenseits der ersten 300 gültigen
    # Anordnungen; Obergrenze zählt nur Kandidaten der besten Stufe). Vorher 94,4 % auf der vollen Messreihe, jetzt
    # 98,6 %; diese Teilmenge 96,6 % (317 von 328), alle Farben gleich.
    rate, total, wrong_colours = _agreement(
        RULESET, sizes=(8, 11, 14, 17), round_counts=(5, 7, 9), seeds=range(4), accelerate=False
    )
    assert total >= 100
    assert rate >= 0.93, f"{rate:.1%} von {total}"
    assert wrong_colours == 0


def _oracle_led_state(n, rounds, seed, played):
    """Stand nach `played` Runden eines Turniers, das bbpPairings selbst fortführt (dieselben Zufallszahlen wie in
    der Messreihe, die diese Fälle gefunden hat: je Partie 42 % Weiß, 42 % Schwarz, 16 % Remis)."""
    from ss_model import DOWN, UP, Pairing, RoundResult

    rng = random.Random(seed * 1000 + n * 10 + rounds)
    players = {r: Player(rank=r) for r in range(1, n + 1)}
    for rnd in range(1, played + 1):
        theirs, bye = run_bbppairings(players, rnd, exe_path=EXE_PATH, total_rounds=rounds)
        floats = {}
        for w, b in theirs:
            if players[w].score != players[b].score:
                high, low = (w, b) if players[w].score > players[b].score else (b, w)
                floats[high], floats[low] = DOWN, UP
        if bye is not None:
            floats[bye] = DOWN
        outcomes = {}
        for w, _ in theirs:
            x = rng.random()
            outcomes[w] = True if x < 0.42 else (False if x < 0.84 else None)
        players = ss_engine.apply_round(players, RoundResult(rnd, tuple(Pairing(w, b) for w, b in theirs), bye, floats), outcomes)
    return players


@needs_oracle
@pytest.mark.parametrize(
    "n, rounds, seed, round_no",
    [
        (14, 9, 2, 3),  # Strom der Bracket-Suche ließ die farblich perfekte Paarung aus; Erzeugungsreihenfolge bei Gleichstand
        (11, 9, 2, 6),  # [C8]: gleich gute Downfloater-Mengen, der Rest der Runde entscheidet
        (11, 9, 3, 7),  # [C7] des aktuellen Blocks steht vor [C8] des nächsten
        (31, 5, 3, 2),  # Runde 2: Farbfehler in der ersten gültigen Anordnung, die perfekte steht dahinter
    ],
)
def test_ruleset_engine_reproduces_cases_that_used_to_differ_from_bbppairings(n, rounds, seed, round_no):
    players = _oracle_led_state(n, rounds, seed, round_no - 1)
    theirs, bye = run_bbppairings(players, round_no, exe_path=EXE_PATH, total_rounds=rounds)
    mine = ss_engine.pair_round(players, round_no, total_rounds=rounds)
    assert {(p.white, p.black) for p in mine.pairings} == {tuple(p) for p in theirs}
    assert mine.bye == bye
