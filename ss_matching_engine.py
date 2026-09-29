"""bbpPairings' EIGENER Algorithmus, treu portiert: EIN einziges gewichtetes Matching-Objekt über die
GESAMTE Runde (alle Spieler, nicht nur eine Bracket), bracket-für-bracket mit inkrementell angepassten
Kantengewichten weitergelöst (`dutch.cpp:645-1690`, vollständig gelesen aus dem geklonten Quellcode,
s. `project_turnierplanung_dag_scoping.md`). EIGENSTÄNDIGES, PARALLELES Modul - NICHT in `ss_engine.py`/
`ss_bracket.py`/`app.py` verdrahtet (bewusste Nutzerentscheidung): die dort implementierte, wörtlich am
FIDE-Regeltext orientierte Bracket-für-Bracket-Suche bleibt unangetastet die Basis der Demo/App. Dieses
Modul existiert, um bbpPairings' TATSÄCHLICHEN Mechanismus unabhängig gegen `bbpPairings.exe` zu verifizieren
- Grund: mehrere Sitzungs-Versuche, den Restgleichstand (~0,5-2,5 % gegen `bbpPairings.exe`) per Tie-Break
auf der bestehenden Architektur zu schließen, scheiterten NACHWEISLICH (siehe `ss_bbp_tiebreak.py`s
Moduldoku, Nachmessung 2026-09-29) - bbpPairings' "Paare/Scores in der nächsten Bracket"-Priorität ist kein
lokal nachrüstbares Signal, sondern Teil EINES global fortgeführten Matchings.

**Endergebnis (2026-09-29)**: **100,000 % auf BEIDEN Stichproben** (1430/1430 Standard-, 1994/1994 härtere
Stichprobe) - exakte Übereinstimmung mit `bbpPairings.exe`. Der letzte verbliebene Fall (1993/1994) war KEIN
Bug in diesem Modul, sondern ein latenter, seit Beginn dieser Sitzungsreihe unentdeckter Fehler in
`ss_colour.allocate` (Art. 5.2.4-Gleichstand: verglich nur nach Rang, NICHT wie bbpPairings' eigenes
`acceleratedScoreRankCompare` zuerst nach SCORE - dutch.cpp:488-514/tournament.h:242-254, per
`bbpPairings.exe -c`-Checkliste direkt gefunden, s. `ss_colour.py`). Da bisher JEDER Sweep dieser
Sitzungsreihe Paarungen nur als `frozenset` (ohne Farbe) verglich, blieb dieser Fehler unsichtbar, obwohl er
über die Farbhistorie in spätere Runden hinein kaskadierte und dort scheinbar unabhängige
Paarungs-STRUKTUR-Mismatches erzeugte - eine Lehre für künftige Sweeps: Farbe separat mitprüfen.

**Wiederverwendet** (siehe Moduldoku der jeweiligen Datei): `ss_model.Player`/`GameRecord`/`Pairing`/
`RoundResult`, `ss_compat.compatible` (treue Portierung derselben Quellfunktion, `dutch.cpp:34-69`),
`ss_colour.allocate` (treue Portierung von Art. 5.2/`choosePlayerColor`, `dutch.cpp:488-516`).
**Bewusst NICHT wiederverwendet**: `ss_quality.colour_terms` - an FIDEs wörtlichem Regeltext kalibriert,
NICHT an bbpPairings' eigener interner Kantengewicht-Kodierung (`insertColorBits`, `dutch.cpp:161-211`,
Quellcode-Fund dieser Sitzung: nicht bitgenau deckungsgleich) - hier frisch portiert.

**Kantengewicht als EIN Python-`int`**: `dutch.cpp` presst alle Prioritätsfelder in ein FEST breites
Integer (C++-Notwendigkeit). Python-`int` ist beliebig groß - hier über eine gemischt-radix-Kodierung mit
GROSSZÜGIGEM, sicherem Radix `_BASE = 10**15` je Feld erreicht (nicht `dutch.cpp`s exakte, knapp bemessene
Bit-Breiten `scoreGroupSizeBits`/`scoreGroupsShift` - deren einziger Zweck ist, dass die SUMME mehrerer
Kanten-Gewichte in einem `networkx.max_weight_matching` nie in ein höher priorisiertes Feld "durchschlägt";
`_BASE` erreicht dieselbe Sicherheit generös, ohne C++s knappe Bit-Buchhaltung nachbilden zu müssen - bei
≤ 32 Spielern/≤16 Kanten je Matching bleibt selbst die Summe aller Kanten in einem Feld um Größenordnungen
unter `_BASE`)."""

from __future__ import annotations

from dataclasses import dataclass, field

import networkx as nx

from ss_colour import ABSOLUTE, STRONG, allocate, classify
from ss_compat import compatible
from ss_model import BLACK, BYE, DOWN, UP, WHITE, Pairing, Player, RoundResult

__all__ = ["pair_round_matching", "NoValidPairingError"]

_BASE = 10**15  # sicherer, großzügiger Radix je Prioritätsfeld (siehe Moduldoku)


class NoValidPairingError(Exception):
    """Art. 1.9.3 - keine [C1]-[C4]-konforme Paarung existiert (dutch.cpp wirft hier
    `NoValidPairingException`, wenn nach dem ersten Matching-Versuch mehr als ein Spieler unversorgt
    bliebe oder der unversorgte Spieler nicht freilosberechtigt ist)."""


def _invert(colour: str) -> str:
    return BLACK if colour == WHITE else WHITE


# --- Farb-Hilfsfunktionen (tournament.cpp:40-91/tournament.h:211-217), aus den bereits vorhandenen
# `Player`-Feldern abgeleitet statt neu im Modell gespeichert - `ss_colour.classify` ist eine bereits
# verifizierte, treue Portierung DERSELBEN Zustands-Herleitung (Quellcode-Fund dieser Sitzung: die
# Priorisierungskette in `tournament.cpp:80-85` entspricht Zeile für Zeile `classify()`s eigener Kette).


def _colour_imbalance(p: Player) -> int:
    return abs(p.colour_difference)


def _repeated_colour(p: Player) -> str | None:
    last_two = p.last_two_colours
    return last_two[0] if len(last_two) == 2 and last_two[0] == last_two[1] else None


def _absolute_colour_imbalance(p: Player) -> bool:
    return _colour_imbalance(p) > 1


def _absolute_colour_preference(p: Player) -> bool:
    return classify(p).strength == ABSOLUTE


def _strong_colour_preference(p: Player) -> bool:
    return classify(p).strength == STRONG


def _colour_preference(p: Player) -> str | None:
    return classify(p).colour


def _colour_preferences_compatible(a: Player, b: Player) -> bool:
    ca, cb = _colour_preference(a), _colour_preference(b)
    return ca != cb or ca is None or cb is None


def _colour_bits(player: Player, opponent: Player) -> tuple[int, int, int, int]:
    """`insertColorBits` (dutch.cpp:161-211), 4 Bits, `player`=lowerPlayer, `opponent`=higherPlayer -
    der Aufrufer maskiert (nur wenn `player` Mitglied der aktuellen Bracket ist, sonst (0,0,0,0))."""
    pref_p, pref_o = _colour_preference(player), _colour_preference(opponent)
    imb_p, imb_o = _colour_imbalance(player), _colour_imbalance(opponent)
    abs_p, abs_o = _absolute_colour_preference(player), _absolute_colour_preference(opponent)
    strong_p, strong_o = _strong_colour_preference(player), _strong_colour_preference(opponent)

    bit1 = (not _absolute_colour_imbalance(player)) or (not _absolute_colour_imbalance(opponent)) or pref_p != pref_o

    if not abs_p or not abs_o or pref_p != pref_o:
        bit2 = True
    elif imb_p == imb_o:
        rep_p, rep_o = _repeated_colour(player), _repeated_colour(opponent)
        bit2 = rep_p is None or rep_p != rep_o
    else:
        heavier = opponent if imb_p > imb_o else player
        bit2 = _repeated_colour(heavier) != _invert(pref_p)

    bit3 = _colour_preferences_compatible(player, opponent)

    bit4 = (not strong_p and not abs_p) or (not strong_o and not abs_o) or (abs_p and abs_o) or pref_p != pref_o

    return (int(bit1), int(bit2), int(bit3), int(bit4))


def _eligible_for_bye(p: Player) -> bool:
    return not p.had_bye_or_equivalent


def _played_games(p: Player) -> int:
    """`tournament::Player::playedGames` (tournament.cpp:53-71): Anzahl ECHT gespielter Partien
    (kein Freilos) - Gegenstück zu `Player.unplayed_games`, das die BYE-Partien zählt."""
    return sum(1 for g in p.games if g.opponent != BYE)


def _is_bye_candidate(p: Player, bye_assignee_score: float) -> bool:
    return _eligible_for_bye(p) and p.score <= bye_assignee_score


def _float_at(p: Player, rounds_back: int) -> str | None:
    hist = p.float_in_last_n_rounds(rounds_back)
    return hist[rounds_back - 1] if len(hist) >= rounds_back else None


@dataclass
class _RoundState:
    """Rundenweit konstante Werte, die `_edge_weight` braucht - einmal berechnet, an jeden Aufruf
    durchgereicht (entspricht `computeMatching`s lokalen Variablen `scoreGroupShifts`,
    `byeAssigneeScore`, `isSingleDownfloaterTheByeAssignee`, `unplayedGameRanks`)."""

    players: dict[int, Player]
    topscorer_threshold: float
    played_rounds: int
    score_rank: dict[float, int] = field(default_factory=dict)  # Score (aufsteigend) -> Index 0,1,2,...
    bye_assignee_score: float = 0.0
    single_downfloater_is_bye_assignee: bool = False
    unplayed_game_ranks: dict[int, int] = field(default_factory=dict)  # gespielte Partien -> Rang


def _edge_weight(
    higher: Player,
    lower: Player,
    lower_in_current: bool,
    lower_in_next: bool,
    st: _RoundState,
) -> int:
    """`computeEdgeWeight` (dutch.cpp:230-482), treu portiert. `higher`/`lower` = die beiden Endpunkte
    EINER Kante, `higher` ist der in Art.-1.2-Reihenfolge FRÜHER gereihte (höherer Score/kleinerer
    Rang bei Gleichstand) - `lower` der SPÄTER gereihte. 0 = keine Kante (C1/C3-Verletzung)."""
    if not compatible(higher, lower, st.topscorer_threshold):
        return 0

    value = 1 + int(not _is_bye_candidate(higher, st.bye_assignee_score)) + int(not _is_bye_candidate(lower, st.bye_assignee_score))

    value = value * _BASE + int(lower_in_current)

    value = value * _BASE + ((1 << st.score_rank[higher.score]) if lower_in_current else 0)

    value = value * _BASE + int(lower_in_next)

    value = value * _BASE + ((1 << st.score_rank[higher.score]) if lower_in_next else 0)

    bye_term = 0
    if st.single_downfloater_is_bye_assignee:
        if higher.score == st.bye_assignee_score:
            bye_term += st.unplayed_game_ranks[_played_games(higher)]
        if lower.score == st.bye_assignee_score:
            bye_term += st.unplayed_game_ranks[_played_games(lower)]
    value = value * _BASE + bye_term

    if lower_in_current:
        b1, b2, b3, b4 = _colour_bits(lower, higher)
    else:
        b1 = b2 = b3 = b4 = 0
    for b in (b1, b2, b3, b4):
        value = value * _BASE + b

    for rounds_back in (1, 2):
        if st.played_rounds < rounds_back:
            value = value * _BASE + 0  # C14/C16-Feld (Platzhalter, exakt wie dutch.cpp - kein Beitrag)
            value = value * _BASE + 0  # C15/C17-Feld
            continue
        if lower_in_current:
            down_term = int(_float_at(lower, rounds_back) == DOWN)
            down_term += int(higher.score <= lower.score and _float_at(higher, rounds_back) == DOWN)
            up_term = int(not (higher.score > lower.score and _float_at(lower, rounds_back) == UP))
        else:
            down_term = up_term = 0
        value = value * _BASE + down_term
        value = value * _BASE + up_term

    for rounds_back in (1, 2):
        if st.played_rounds < rounds_back:
            value = value * _BASE + 0
            value = value * _BASE + 0
            continue
        if lower_in_current:
            score_down_term = 0
            if _float_at(lower, rounds_back) == DOWN:
                score_down_term += 1 << st.score_rank[lower.score]
            if _float_at(higher, rounds_back) == DOWN:
                score_down_term += 1 << st.score_rank[higher.score]
            score_up_term = int(not (_float_at(lower, rounds_back) == UP and higher.score > lower.score))
            score_up_term = score_up_term << st.score_rank[higher.score] if score_up_term else 0
        else:
            score_down_term = score_up_term = 0
        value = value * _BASE + score_down_term
        value = value * _BASE + score_up_term

    # Reservierter Platz am unteren Ende (dutch.cpp:462-469, "leave room for enforcing the ordering
    # requirements") - hier gefüllt von `_boosted_weight`s Zusatzterm (die spätere, PERMANENTE
    # inkrementelle Anpassung aus der Bracket-Hauptschleife, s. dort), nicht von dieser Funktion selbst.
    return value * _BASE


def _boosted_weight(a: int, b: int, base_weight_fn, boosts: dict[frozenset[int, int], int]) -> int:
    """Wendet die akkumulierten, PERMANENTEN Kantengewicht-Anpassungen (`dutch.cpp`s wiederholte,
    NIE zurückgesetzte `matchingComputer.setEdgeWeight`-Aufrufe innerhalb der Bracket-Hauptschleife -
    anders als `ss_bbp_tiebreak.py`s testweise-und-zurückgesetzte Störungen) auf das Basisgewicht an.
    `boosts`-Werte bleiben klein genug (siehe Aufrufer), um NIE in das reservierte Feld der jeweils
    NÄCHSTHÖHEREN Basispriorität durchzuschlagen."""
    base = base_weight_fn(a, b)
    if not base:
        return 0
    return base + boosts.get(frozenset((a, b)), 0)


def _solve(pool: list[int], weight_fn) -> dict[int, int]:
    """EIN frischer `networkx`-Löser je Aufruf (reine C++-Performance-Optimierung wird hier zur
    Neuberechnung - siehe `ss_bbp_tiebreak.py`s Moduldoku für dieselbe Begründung; bei ≤32 Spielern
    unproblematisch). `maxcardinality=False`: die "möglichst viele Paare"-Präferenz steckt bereits als
    höchstprioritäres Feld IN den Gewichten (dutch.cpp löst ebenfalls ein einfaches gewichtetes, kein
    kardinalitätsbeschränktes Matching)."""
    graph = nx.Graph()
    graph.add_nodes_from(pool)
    ordered = sorted(pool)
    for i, a in enumerate(ordered):
        for b in ordered[i + 1 :]:
            w = weight_fn(a, b)
            if w:
                graph.add_edge(a, b, weight=w)
    mate_pairs = nx.max_weight_matching(graph, maxcardinality=False)
    mate: dict[int, int] = {}
    for a, b in mate_pairs:
        mate[a] = b
        mate[b] = a
    return mate


def _art12_key(rank: int, players: dict[int, Player]) -> tuple[float, int]:
    return (-players[rank].score, rank)


def _order_pair(a: int, b: int, players: dict[int, Player]) -> tuple[int, int]:
    """(higher, lower) in Art.-1.2-Reihenfolge (Score absteigend, dann Rang aufsteigend) - `_solve`s
    interne Graph-Kantenreihenfolge (nach Rangnummer, nur für Determinismus) sagt NICHTS darüber, wer
    von zwei Rängen in Art.-1.2-Sinn `higher`/`lower` ist - jede `weight_fn`-Closure muss das SELBST
    herstellen, nicht von der Aufrufreihenfolge annehmen."""
    return (a, b) if _art12_key(a, players) < _art12_key(b, players) else (b, a)


def _groups(players: dict[int, Player]) -> list[tuple[float, list[int]]]:
    """Art. 1.2: Score absteigend, je Score Rang aufsteigend."""
    by_score: dict[float, list[int]] = {}
    for r, p in players.items():
        by_score.setdefault(p.score, []).append(r)
    for ranks in by_score.values():
        ranks.sort()
    return sorted(by_score.items(), key=lambda kv: -kv[0])


def _score_ranks(players: dict[int, Player]) -> dict[float, int]:
    """Jedem in dieser Runde vorkommenden Score EINEN aufsteigenden Index zuordnen (0 = niedrigster
    Score) - Entsprechung zu `scoreGroupShifts` (dutch.cpp:685-712), hier ohne Bit-Breiten-Buchhaltung
    (siehe Moduldoku)."""
    distinct = sorted({p.score for p in players.values()})
    return {score: i for i, score in enumerate(distinct)}


def _bye_probe_weight(player: Player, opponent: Player, score_rank: dict[float, int], top_score: float) -> int:
    """Grobe erste Gewichtung NUR für den Freilos-Vorlauf bei ungerader Teilnehmerzahl
    (dutch.cpp:766-791) - bewusst NICHT dieselbe wie `_edge_weight` (dort wird u. a. `playerScore >=
    topScore` NUR für den positional SPÄTEREN der beiden Spieler abgefragt, asymmetrisch)."""
    w = 1 + int(not _eligible_for_bye(player)) + int(not _eligible_for_bye(opponent))
    w = w * _BASE + (score_rank[player.score] + score_rank[opponent.score])
    w = w * _BASE + int(player.score >= top_score)
    return w


def _determine_bye(
    sorted_ranks: list[int], players: dict[int, Player], score_rank: dict[float, int], topscorer_threshold: float
) -> tuple[float, bool, dict[int, int]]:
    """dutch.cpp:819-930: liefert (`byeAssigneeScore`, `isSingleDownfloaterTheByeAssignee`,
    `unplayedGameRanks`). Bei gerader Teilnehmerzahl (kein Freilos nötig) alle Werte neutral."""
    n = len(sorted_ranks)
    if n % 2 == 0:
        return 0.0, False, {}

    top_score = players[sorted_ranks[0]].score

    def weight_fn(a: int, b: int) -> int:
        higher, lower = _order_pair(a, b, players)
        if not compatible(players[higher], players[lower], topscorer_threshold):
            return 0
        return _bye_probe_weight(players[lower], players[higher], score_rank, top_score)

    mate = _solve(sorted_ranks, weight_fn)
    unmatched = [r for r in sorted_ranks if r not in mate]
    if len(unmatched) != 1 or not _eligible_for_bye(players[unmatched[0]]):
        raise NoValidPairingError("keine gültige Rundenpaarung gefunden (Art. 1.9.3)")
    bye_rank = unmatched[0]
    bye_assignee_score = players[bye_rank].score

    single_downfloater_is_bye = bye_assignee_score >= top_score
    if single_downfloater_is_bye:
        for r in sorted_ranks:
            p = players[r]
            if p.score < top_score:
                break
            partner = mate.get(r)
            if partner is None or players[partner].score < top_score:
                single_downfloater_is_bye = False
                break

    tied = [r for r in sorted_ranks if players[r].score == bye_assignee_score]
    played_counts = sorted((_played_games(players[r]) for r in tied), reverse=True)
    unplayed_game_ranks = {pg: i for i, pg in enumerate(played_counts)}

    return bye_assignee_score, single_downfloater_is_bye, unplayed_game_ranks


# --- Rest/Austausch (dutch.cpp:1257-1507) - adaptiert aus `ss_bbp_tiebreak.py`s bereits gegen das
# Orakel verifizierter Fassung (dieselbe Arithmetik), hier auf den GESAMTEN aktiven Rundenpool
# skaliert (nicht nur zwei Brackets) - treuer zum echten, rundenweiten `matchingComputer`. -----------

_REMAINDER_SCALE = 10**6  # groß genug, dass der Zusatzterm nie das Basisgewicht verfälscht


def _remainder_weight(
    x: int,
    y: int,
    base_weight_fn,
    position: dict[int, int],
    remainder_pairs: int,
    perturbation: dict[tuple[int, int], int] | None = None,
) -> int:
    base = base_weight_fn(x, y)
    if not base:
        return 0
    smaller, larger = (x, y) if position[x] < position[y] else (y, x)
    in_first_group = int(position[smaller] < remainder_pairs)
    addend = in_first_group * (len(position) + 1) - position[smaller]
    weight = base * _REMAINDER_SCALE + (len(position) + 1) + addend
    if perturbation:
        key = (smaller, larger)
        if key in perturbation:
            weight += perturbation[key]
    return weight


def _split_remainder(remainder: list[int], mate: dict[int, int]) -> tuple[int, list[int], list[int]]:
    position = {r: i for i, r in enumerate(remainder)}
    remainder_set = set(remainder)
    remainder_pairs = 0
    for r in remainder:
        partner = mate.get(r)
        if partner in remainder_set and position[partner] < position[r]:
            remainder_pairs += 1
    return remainder_pairs, remainder[:remainder_pairs], remainder[remainder_pairs:]


def _exchange_count(pool: list[int], base_weight_fn, remainder: list[int], remainder_pairs: int) -> tuple[int, dict[int, int]]:
    position = {r: i for i, r in enumerate(remainder)}

    def weight_fn(x: int, y: int) -> int:
        if x in position and y in position:
            return _remainder_weight(x, y, base_weight_fn, position, remainder_pairs)
        base = base_weight_fn(x, y)
        return 0 if not base else base * _REMAINDER_SCALE

    mate = _solve(pool, weight_fn)

    target = 0
    for r in remainder[:remainder_pairs]:
        partner = mate.get(r)
        if partner is None or position.get(partner, -1) < position[r]:
            target += 1
    return target, mate


def _greedy_scan(
    pool: list[int],
    base_weight_fn,
    remainder: list[int],
    remainder_pairs: int,
    mate: dict[int, int],
    locked_zero: set[frozenset],
    *,
    target: int,
    scan_first_group: bool,
) -> dict[int, int]:
    """`locked_zero`: vom Aufrufer (der `_Engine`) bereitgestellte, GETEILTE, PERMANENTE Sperrmenge
    (entspricht `dutch.cpp`s direktem `baseEdgeWeights[...] &= 0u` auf der geteilten Gewichtstabelle,
    NICHT einer lokal-flüchtigen Kopie) - bestätigte Tausche bleiben auch für NACHFOLGENDE Stufen
    (die finale Gegner-Zuweisung, `dutch.cpp:1509-1599`) gesperrt, nicht nur innerhalb dieses Scans."""
    position = {r: i for i, r in enumerate(remainder)}

    def base_or_locked(x: int, y: int) -> int:
        if frozenset((x, y)) in locked_zero:
            return 0
        return base_weight_fn(x, y)

    def weight_fn(x: int, y: int) -> int:
        if x in position and y in position:
            return _remainder_weight(x, y, base_or_locked, position, remainder_pairs)
        base = base_or_locked(x, y)
        return 0 if not base else base * _REMAINDER_SCALE

    remaining = target
    sequence = list(reversed(remainder[:remainder_pairs])) if scan_first_group else remainder[remainder_pairs:]

    for player in sequence:
        if remaining <= 0:
            break
        pos_player = position[player]
        partner = mate.get(player)
        currently_forward = partner is not None and position.get(partner, -1) > pos_player
        already_exchanged = partner is not None and position.get(partner, -1) < pos_player

        if scan_first_group:
            candidates_to_nudge = [r for r in remainder if position[r] > pos_player]
            nudge = -1
            must_be_default_state = currently_forward
        else:
            candidates_to_nudge = [r for r in remainder if position[r] < pos_player]
            nudge = +1
            must_be_default_state = not already_exchanged

        if must_be_default_state and candidates_to_nudge:
            perturbation = {}
            for opp in candidates_to_nudge:
                key = (player, opp) if player < opp else (opp, player)
                w = base_or_locked(*key)
                if w:
                    perturbation[key] = nudge

            def perturbed_weight_fn(x: int, y: int, _pert=perturbation) -> int:
                if x in position and y in position:
                    return _remainder_weight(x, y, base_or_locked, position, remainder_pairs, _pert)
                base = base_or_locked(x, y)
                return 0 if not base else base * _REMAINDER_SCALE

            mate = _solve(pool, perturbed_weight_fn)

        new_partner = mate.get(player)
        new_pos = position.get(new_partner, -1) if new_partner is not None else -1
        if scan_first_group:
            exchanged = new_partner is None or new_pos <= pos_player
        else:
            exchanged = new_partner is not None and pos_player < new_pos < remainder_pairs

        if exchanged:
            remaining -= 1
            for opp in candidates_to_nudge:
                locked_zero.add(frozenset((player, opp)))

        mate = _solve(pool, weight_fn)

    return mate


def _pending_score_groups(pending: list[int], players: dict[int, Player]) -> list[list[int]]:
    groups: list[list[int]] = []
    i = 0
    while i < len(pending):
        score = players[pending[i]].score
        j = i
        while j < len(pending) and players[pending[j]].score == score:
            j += 1
        groups.append(pending[i:j])
        i = j
    return groups


class _Engine:
    """EIN geteilter Zustand über die GESAMTE Runde (entspricht `dutch.cpp`s einzigem, inkrementell
    fortgeführtem `matchingComputer`): `active` (noch nicht fixierte Ränge), `edge_boost` (permanente
    additive Anpassungen, NIE zurückgesetzt - `matchingComputer.setEdgeWeight`-Aufrufe, die nicht
    wieder rückgängig gemacht werden) und `locked_zero` (permanent auf 0 gesperrte Kanten -
    `baseEdgeWeights[...] &= 0u`). Jeder `solve()`-Aufruf baut frisch einen `networkx`-Graphen über
    den aktuellen `active`-Pool (reine Performance- statt Korrektheitsabwägung, s. Moduldoku)."""

    def __init__(self, players: dict[int, Player], topscorer_threshold: float, played_rounds: int):
        self.players = players
        self.st = _RoundState(players=players, topscorer_threshold=topscorer_threshold, played_rounds=played_rounds)
        self.active: set[int] = set(players)
        self.edge_boost: dict[frozenset, int] = {}
        self.locked_zero: set[frozenset] = set()
        self.finalized_pairs: dict[int, int] = {}

    def base_weight(self, a: int, b: int, current_window: set[int], next_window: set[int]) -> int:
        if frozenset((a, b)) in self.locked_zero:
            return 0
        higher, lower = _order_pair(a, b, self.players)
        return _edge_weight(self.players[higher], self.players[lower], lower in current_window, lower in next_window, self.st)

    def edge_weight(self, a: int, b: int, current_window: set[int], next_window: set[int]) -> int:
        base = self.base_weight(a, b, current_window, next_window)
        if not base:
            return 0
        return base + self.edge_boost.get(frozenset((a, b)), 0)

    def weight_fn(self, current_window: set[int], next_window: set[int]):
        return lambda a, b: self.edge_weight(a, b, current_window, next_window)

    def solve(self, current_window: set[int], next_window: set[int]) -> dict[int, int]:
        return _solve(sorted(self.active), self.weight_fn(current_window, next_window))

    def add_boost(self, a: int, b: int, amount: int) -> None:
        key = frozenset((a, b))
        self.edge_boost[key] = self.edge_boost.get(key, 0) + amount

    def finalize_pair(self, a: int, b: int) -> None:
        self.finalized_pairs[a] = b
        self.finalized_pairs[b] = a
        self.active.discard(a)
        self.active.discard(b)

    def _boost_edges_to(self, r: int, targets, amount: int, current_window: set[int], next_window: set[int]) -> None:
        for opp in targets:
            if opp == r:
                continue
            if self.base_weight(r, opp, current_window, next_window):
                self.add_boost(r, opp, amount)

    # --- dutch.cpp:1091-1205 "Choose the moved down players to pair in the current pairing bracket" -

    def _choose_moved_down(
        self, pending: list[int], current_window: set[int], next_window: set[int], mate: dict[int, int]
    ) -> tuple[set[int], dict[int, int]]:
        matched_pending: set[int] = set()
        for subgroup in _pending_score_groups(pending, self.players):
            remaining_total = len(subgroup)
            remaining_matched = sum(1 for r in subgroup if mate.get(r) in current_window)
            for r in subgroup:
                if remaining_matched == 0:
                    continue
                if remaining_total <= remaining_matched:
                    matched_pending.add(r)
                    continue
                remaining_total -= 1
                if mate.get(r) not in current_window:
                    self._boost_edges_to(r, current_window, 1, current_window, next_window)
                    mate = self.solve(current_window, next_window)
                if mate.get(r) in current_window:
                    matched_pending.add(r)
                    remaining_matched -= 1
                    self._boost_edges_to(r, current_window, len(current_window) + 1, current_window, next_window)
        return matched_pending, mate

    # --- dutch.cpp:1207-1255 "Choose the opponents of the moved down players" ----------------------

    def _choose_opponents(
        self, pending: list[int], current_window: set[int], next_window: set[int], matched_pending: set[int], mate: dict[int, int]
    ) -> dict[int, int]:
        residents_window = [r for r in current_window if r not in pending]
        for r in pending:  # bereits Art.-1.2-sortiert
            if r not in matched_pending or r not in self.active:
                continue
            targets = sorted(
                (x for x in residents_window if x in self.active),
                key=lambda x: _art12_key(x, self.players),
                reverse=True,
            )
            addend = 1
            for opp in targets:
                if self.base_weight(r, opp, current_window, next_window):
                    self.add_boost(r, opp, addend)
                    addend += 1
            mate = self.solve(current_window, next_window)  # geteilte `stableMatching` weiterreichen
            partner = mate.get(r)
            if partner is not None:
                self.finalize_pair(r, partner)
        return mate

    # --- dutch.cpp:1257-1507 Rest/Austausch, adaptiert aus den Modulfunktionen oben ------------------

    def _remainder_exchange(
        self, residents: list[int], current_window: set[int], next_window: set[int], mate: dict[int, int]
    ) -> tuple[list[int], int, dict[int, int]]:
        # dutch.cpp:1270-1285: `remainder` umfasst NUR das AKTUELLE Fenster (Pending+Residenten dieser
        # Bracket, `[scoreGroupBegin, nextScoreGroupBegin)`) - NICHT die nächste Bracket. Ein
        # Remainder-Mitglied DARF trotzdem mit jemandem aus `next_window` gepaart sein (das IST genau
        # der "kreuzt in die nächste Bracket"-Fall) - dessen Partner liegt dann einfach AUSSERHALB
        # `remainder`, nicht in `position`. Echter, in dieser Sitzung gefundener Strukturfehler: eine
        # frühere Fassung nahm next_window fälschlich MIT in `remainder` auf, was `remainder_pairs`
        # systematisch verfälschte (jedes bereits über die Bracket-Grenze geschlossene Paar zählte
        # dann fälschlich als "lokal geschlossen").
        remainder = sorted((r for r in current_window if r in self.active), key=lambda r: _art12_key(r, self.players))
        remainder_pairs, _first, _second = _split_remainder(remainder, mate)
        if not remainder or remainder_pairs == 0 or remainder_pairs == len(remainder):
            return remainder, remainder_pairs, mate

        base_fn = self.weight_fn(current_window, next_window)
        pool = sorted(self.active)
        target, mate = _exchange_count(pool, base_fn, remainder, remainder_pairs)
        if target:
            mate = _greedy_scan(pool, base_fn, remainder, remainder_pairs, mate, self.locked_zero, target=target, scan_first_group=True)
            mate = _greedy_scan(pool, base_fn, remainder, remainder_pairs, mate, self.locked_zero, target=target, scan_first_group=False)
        return remainder, remainder_pairs, mate

    # --- dutch.cpp:1509-1543 "Finalize which players will be exchanged, and reset the bits we used
    # for determining that" - permanent Sperrungen für Paare, bei denen `player` nach dem Scan KEINEN
    # gültigen Vorwärts-Partner (innerhalb `remainder`) hat, ODER `opponent` selbst schon einen EIGENEN
    # Vorwärts-Partner hat (dann darf er nicht als Ziel für `player` umgeleitet werden). Setzt außerdem
    # implizit die Gewichte auf die reine Basis zurück - bei uns automatisch, da die nachfolgende Stufe
    # wieder `self.base_weight`/`self.solve` statt der `_remainder_weight`-Skalierung benutzt.

    def _finalize_remainder_locks(self, remainder: list[int], mate: dict[int, int]) -> None:
        position = {r: i for i, r in enumerate(remainder)}

        def is_forward(r: int) -> bool:
            partner = mate.get(r)
            return partner is not None and partner in position and position[partner] > position[r]

        for i, player in enumerate(remainder):
            player_forward = is_forward(player)
            for opponent in remainder[i + 1 :]:
                if not player_forward or is_forward(opponent):
                    self.locked_zero.add(frozenset((player, opponent)))

    # --- dutch.cpp:1545-1599 "Choose the players to be paired with each of the players in the first
    # group" - finale Gegner-Zuweisung für die im Rest/Austausch bestätigt VERBLEIBENDEN Residenten --

    def _choose_partners_for_remainder(self, remainder: list[int], current_window: set[int], next_window: set[int], mate: dict[int, int]) -> None:
        position = {r: i for i, r in enumerate(remainder)}
        for player in remainder:
            if player not in self.active:
                continue
            partner = mate.get(player)
            if partner is None or partner not in position or not (position[partner] > position[player]):
                continue
            candidates = sorted(
                (r for r in remainder if position[r] > position[player] and r in self.active),
                key=lambda r: position[r],
                reverse=True,
            )
            addend = 0
            for opp in candidates:
                if self.base_weight(player, opp, current_window, next_window):
                    self.add_boost(player, opp, addend)
                    addend += 1
            mate = self.solve(current_window, next_window)  # geteilte `stableMatching` weiterreichen
            match = mate.get(player)
            if match is not None:
                self.finalize_pair(player, match)

    # --- Hauptschleife (dutch.cpp:955-1650) -----------------------------------------------------

    def run(self) -> None:
        sorted_ranks = sorted(self.players, key=lambda r: _art12_key(r, self.players))
        self.st.score_rank = _score_ranks(self.players)
        bye_score, single_dl_bye, upr = _determine_bye(sorted_ranks, self.players, self.st.score_rank, self.st.topscorer_threshold)
        self.st.bye_assignee_score = bye_score
        self.st.single_downfloater_is_bye_assignee = single_dl_bye
        self.st.unplayed_game_ranks = upr

        n_total = len(self.players)
        groups = _groups(self.players)
        pending: list[int] = []
        for gi, (_score, residents) in enumerate(groups):
            current_window = set(pending) | set(residents)
            next_window = set(groups[gi + 1][1]) if gi + 1 < len(groups) else set()

            # dutch.cpp:1607-1611: `isSingleDownfloaterTheByeAssignee` gilt NUR bracket-lokal, nicht
            # rundenweit fest - VOR jeder Bracket neu geprüft (ungerade Gesamtzahl UND es gibt
            # überhaupt eine nächste Bracket UND deren Score ist NICHT über dem Freilos-Score).
            self.st.single_downfloater_is_bye_assignee = (
                n_total % 2 == 1 and gi + 1 < len(groups) and self.st.bye_assignee_score >= groups[gi + 1][0]
            )

            mate = self.solve(current_window, next_window)
            matched_pending, mate = self._choose_moved_down(pending, current_window, next_window, mate)
            mate = self._choose_opponents(pending, current_window, next_window, matched_pending, mate)

            remainder, _remainder_pairs, mate = self._remainder_exchange(residents, current_window, next_window, mate)
            self._finalize_remainder_locks(remainder, mate)
            self._choose_partners_for_remainder(remainder, current_window, next_window, mate)

            pending = sorted((r for r in current_window if r in self.active), key=lambda r: _art12_key(r, self.players))

        if len(pending) > 1:
            raise NoValidPairingError("keine gültige Rundenpaarung gefunden (Art. 1.9.3)")
        self._trailing_bye = pending[0] if pending else None


def pair_round_matching(players: dict[int, Player], round_no: int, total_rounds: int | None = None) -> RoundResult:
    """Eigenständiger Einstiegspunkt, Rückgabeformat wie `ss_engine.pair_round` (`RoundResult`) für
    direkte Vergleichbarkeit - siehe Moduldoku: bewusst NICHT `ss_engine.pair_round` ersetzend."""
    max_possible_score = float(total_rounds) if total_rounds is not None else float(max(round_no - 1, 0))
    topscorer_threshold = max_possible_score / 2.0
    played_rounds = max(round_no - 1, 0)

    engine = _Engine(players, topscorer_threshold, played_rounds)
    engine.run()

    pairings: list[Pairing] = []
    float_direction: dict[int, str] = {}
    seen: set[int] = set()
    for a, b in engine.finalized_pairs.items():
        if a in seen:
            continue
        seen.add(a)
        seen.add(b)
        pa, pb = players[a], players[b]
        pairings.append(allocate(pa, pb))
        if pa.score != pb.score:
            downfloater, upfloater = (a, b) if pa.score > pb.score else (b, a)
            float_direction[downfloater] = DOWN
            float_direction[upfloater] = UP

    bye_rank = getattr(engine, "_trailing_bye", None)
    if bye_rank is not None:
        float_direction[bye_rank] = DOWN

    return RoundResult(round_no=round_no, pairings=tuple(pairings), bye=bye_rank, float_directions=float_direction)
