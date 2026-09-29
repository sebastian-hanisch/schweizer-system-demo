"""Orchestrierung: die Runde wird Bracket für Bracket gelöst (Score absteigend, Art. 1.9.2), genau
wie es der FIDE-Regeltext selbst vorschreibt - NICHT als ein globales gewichtetes Matching über
die ganze Runde (das war ein früherer, inzwischen verworfener Ansatz, der sich eher an bbpPairings'
eigener C++-Implementierungsstrategie orientierte als am Regeltext selbst - siehe
project_turnierplanung_dag_scoping.md).

Jede Bracket liefert `ss_bracket.solve_bracket(...)` als LAZY Folge von Kandidaten in
Prioritätsreihenfolge (Art. 3.8.1), nicht nur EINEN geschätzten besten. `_solve_round` probiert für
jeden Kandidaten ECHT (per Rekursion), ob sich damit die RESTLICHE Runde zu Ende lösen lässt - erst
wenn das fehlschlägt, wird der nächste Kandidat versucht. Drei Stufen pro Bracket (siehe dortige
Doku): (1) eigenes Maximum UND die GESAMTE restliche Kette (beliebig tief, nicht nur die
unmittelbar nächste Bracket) löst OHNE jede Reduktion; (2) eigenes Maximum, Rest darf reduzieren;
(3) nur wenn die Bracket selbst reduzieren darf, auch kleinere Paarzahlen. Stufe (1) ersetzt eine
frühere Fassung, die nur die UNMITTELBAR NÄCHSTE Bracket per einzelnem Kardinalitäts-Matching
SCHÄTZTE (schnell, aber nachweislich manchmal zu kurzsichtig - siehe project_turnierplanung_dag_scoping.md:
sowohl der ursprüngliche dutch_2025_C5-Fund als auch spätere mehrstufige Kaskaden brauchten echtes,
beliebig tiefes Nachprüfen statt eines 1-Schritt-Blicks). Da diese Rekursion selbst schnell abbricht,
sobald ein Kandidat funktioniert, bleibt sie trotz beliebiger Tiefe performant."""

from __future__ import annotations

from ss_blossom import maximum_cardinality_matching
from ss_bracket import BracketContext, NoValidPairingError, solve_bracket
from ss_colour import allocate
from ss_compat import compatible
from ss_model import BYE, DOWN, GameRecord, Pairing, Player, RoundResult, UP

__all__ = ["pair_round", "apply_round", "NoValidPairingError"]

MAX_ROUND_BUDGET = 200_000  # Deckel für die GESAMTZAHL an Kandidaten-Versuchen über die ganze
# rekursive Rundenlösung (alle Brackets zusammen) - verhindert pathologisches Backtracking


def _scoregroups(active_players: dict[int, Player]) -> list[tuple[float, list[int]]]:
    by_score: dict[float, list[int]] = {}
    for r, p in active_players.items():
        by_score.setdefault(p.score, []).append(r)
    for group in by_score.values():
        group.sort()
    return sorted(by_score.items(), key=lambda kv: -kv[0])


def _solve_round(
    groups: list[tuple[float, list[int]]],
    mdps: list[int],
    players: dict[int, Player],
    topscorer_threshold: float,
    allow_reduction: bool,
    budget: list[int],
    excluded_from_bye: frozenset[int] = frozenset(),
    cache: dict | None = None,
) -> tuple[list[tuple[int, int]], int | None] | None:
    """`excluded_from_bye`: NUR für die [C5]-Verbesserung in `pair_round` - Ränge, die für DIESEN
    Suchversuch künstlich als "schon freilosberechtigt ausgeschöpft" gelten, um die Suche zu einer
    ECHTEN Alternative zu zwingen (siehe dortige Doku).

    `cache`: über die GANZE Rundenlösung geteiltes Memo - dieselbe "restliche Kette + dieselben MDPs"
    taucht oft MEHRFACH auf (verschiedene Kandidaten einer früheren Bracket können zum selben Rest
    führen, und die neue [C8]-Stufe unten prüft die GESAMTE Kette per echter Rekursion statt nur
    einen Schritt) - ohne Memo kann das bei größeren/verzweigten Feldern kombinatorisch teuer werden
    (gemessener Fund: einzelne 31-32-Spieler-Saatwerte brauchten bis zu 44s). Score-Folge statt
    id(groups) als Schlüsselteil: `groups` ist immer nach eindeutigen Scores sortiert, die Score-Folge
    identifiziert ein Suffix eindeutig - id() wäre riskant (CPython kann Adressen wiederverwenden)."""
    key = (tuple(score for score, _ in groups), tuple(sorted(mdps)), allow_reduction, excluded_from_bye)
    if cache is not None and key in cache:
        return cache[key]

    result = _solve_round_uncached(groups, mdps, players, topscorer_threshold, allow_reduction, budget, excluded_from_bye, cache)
    # NICHT cachen, wenn ein negatives Ergebnis (None) durch ERSCHÖPFTES Budget statt durch echtes
    # Durchprobieren ALLER Kandidaten zustande kam - `budget` wird über den GANZEN Rekursionsbaum
    # geteilt, und ein späterer Aufruf (z. B. der zweite Durchgang in `_solve_round_both_passes`, mit
    # frischem Budget) könnte für DENSELBEN Schlüssel durchaus noch fündig werden. Ein fälschlich
    # gecachtes "unlösbar" wäre ein echter Korrektheitsfehler, kein bloßer Performance-Verlust.
    if cache is not None and (result is not None or budget[0] > 0):
        cache[key] = result
    return result


def _solve_round_uncached(
    groups: list[tuple[float, list[int]]],
    mdps: list[int],
    players: dict[int, Player],
    topscorer_threshold: float,
    allow_reduction: bool,
    budget: list[int],
    excluded_from_bye: frozenset[int],
    cache: dict | None,
) -> tuple[list[tuple[int, int]], int | None] | None:
    if not groups:
        if not mdps:
            return [], None
        if len(mdps) == 1:
            candidate = mdps[0]
            if not players[candidate].had_bye_or_equivalent and candidate not in excluded_from_bye:  # C2
                return [], candidate
        return None  # Art. 1.9.3: unlösbar (0 Brackets mehr, aber >=2 oder ein nicht-freilosfähiger MDP übrig)

    _, residents = groups[0]
    rest_groups = groups[1:]
    n_residents = len(residents)
    structural_max_pairs = min((n_residents + len(mdps)) // 2, n_residents)

    ctx = BracketContext(players=players, topscorer_threshold=topscorer_threshold)
    tried: set[tuple] = set()
    # Statisch pro Rekursionsebene (unabhängig davon, welcher Kandidat in DIESER Bracket am Ende
    # gewinnt) - nur zur Weitergabe an `solve_bracket`s `_downfloat_cascade_depth_bias`.
    next_group_residents = tuple(rest_groups[0][1]) if rest_groups else ()

    # Drei Stufen (Art. 2.4.1 [C6] hat Vorrang, [C8]/Art. 2.4.3 danach - beide ECHT per Rekursion
    # nachgeprüft, nicht per 1-Schritt-Heuristik geschätzt): zuerst Kandidaten, die IHR EIGENES
    # strukturelles Maximum erreichen UND bei denen die GESAMTE restliche Kette (beliebig tief, nicht
    # nur die unmittelbar nächste Bracket) ganz ohne Reduktion durchlöst; danach dieselben Kandidaten
    # mit einer Rest-Lösung, die selbst reduzieren darf; erst wenn GAR KEINER davon zu einer
    # vollständigen Rundenlösung führt (und nur wenn diese Bracket selbst reduzieren darf), auch
    # Kandidaten unter dem eigenen Maximum. Die "Rest ganz ohne Reduktion"-Stufe ist einfach ein
    # rekursiver Aufruf mit `allow_reduction=False` - dieselbe Maschinerie, die schon `pair_round`
    # für den allerersten (äußersten) Versuch nutzt, jetzt konsequent auf JEDER Ebene angewendet.
    tiers = [(False, False), (False, True)]
    if allow_reduction:
        tiers.append((True, True))

    for candidate_may_reduce, downstream_may_reduce in tiers:
        for candidate in solve_bracket(residents, mdps, ctx, next_group_residents):
            if budget[0] <= 0:
                return None
            if not candidate_may_reduce and len(candidate.pairs) < structural_max_pairs:
                break  # weitere (noch kleinere) Paarzahlen sind auf dieser Stufe ohnehin nicht besser
            key = (candidate.downfloaters, downstream_may_reduce)
            if key in tried:
                continue
            tried.add(key)
            budget[0] -= 1
            rest = _solve_round(
                rest_groups, list(candidate.downfloaters), players, topscorer_threshold, downstream_may_reduce, budget, excluded_from_bye, cache
            )
            if rest is not None:
                rest_pairs, rest_bye = rest
                return list(candidate.pairs) + rest_pairs, rest_bye
    return None


def _global_matching_fallback(
    active_players: dict[int, Player], topscorer_threshold: float
) -> tuple[list[tuple[int, int]], int | None] | None:
    """Letzter Rettungsanker auf Rundenebene: falls selbst das echte Backtracking in `_solve_round`
    (begrenzt durch `MAX_ROUND_BUDGET`) keine Lösung findet, ABER irgendeine global [C1]-[C3]-konforme
    Paarung (ohne Rücksicht auf Bracket-Struktur oder Qualitätskriterien C6-C21) existiert, wird DIE
    verwendet, statt fälschlich [C4]/Art. 1.9.3 zu melden. Bewusster Kompromiss: Korrektheit (eine
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


MAX_BYE_IMPROVEMENT_ATTEMPTS = 6  # zusätzliche volle Suchversuche, um [C5]/[C9] am Freilos zu verbessern


def _solve_round_both_passes(
    groups: list[tuple[float, list[int]]], players: dict[int, Player], topscorer_threshold: float, excluded_from_bye: frozenset[int]
) -> tuple[list[tuple[int, int]], int | None] | None:
    cache: dict = {}
    result = _solve_round(
        groups, [], players, topscorer_threshold, allow_reduction=False, budget=[MAX_ROUND_BUDGET], excluded_from_bye=excluded_from_bye, cache=cache
    )
    if result is None:
        result = _solve_round(
            groups, [], players, topscorer_threshold, allow_reduction=True, budget=[MAX_ROUND_BUDGET], excluded_from_bye=excluded_from_bye, cache=cache
        )
    return result


def _bye_key(bye_rank: int, players: dict[int, Player]) -> tuple[float, int]:
    p = players[bye_rank]
    return p.score, p.unplayed_games  # [C5] dann [C9], beide zu minimieren


def _improve_bye_assignment(
    groups: list[tuple[float, list[int]]], players: dict[int, Player], topscorer_threshold: float, pairs: list[tuple[int, int]], bye_rank: int
) -> tuple[list[tuple[int, int]], int]:
    """[C5]/[C9] werden von `_solve_round` selbst NICHT geprüft (sie betreffen nur den EINEN
    Freilos-Empfänger am Ende der Kette, nicht die Bracket-lokale Kandidatenauswahl) - hier
    nachträglich, mit gezielten, beschränkt vielen Suchversuchen: JEDER bereits AUSPROBIERTE
    Freilos-Empfänger (nicht nur der aktuell BESTE) wird für den nächsten Versuch künstlich als
    "schon gehabt" markiert, damit jeder Versuch eine tatsächlich NEUE Alternative liefert - das
    beste gefundene Ergebnis gewinnt. Bricht früh ab, sobald der bewiesen niedrigstmögliche Score
    erreicht ist, oder wenn keine Alternative mehr gefunden wird.

    (Frühere Fassung schloss nur den aktuell BESTEN Empfänger aus: sobald ein Versuch nicht
    verbesserte, blieb `best_bye` unverändert, also blieb auch `excluded` unverändert - jeder
    weitere Versuch wiederholte deterministisch exakt dieselbe, bereits erfolglose Suche. Gemessener
    Fund: ein 31-Spieler-Saatwert lief dadurch 6-mal denselben ~3s-Suchlauf statt 6 verschiedene.)"""
    eligible_scores = [p.score for p in players.values() if not p.had_bye_or_equivalent]
    if not eligible_scores:
        return pairs, bye_rank
    best_possible_score = min(eligible_scores)

    best_pairs, best_bye = pairs, bye_rank
    excluded: frozenset[int] = frozenset({bye_rank})
    for _ in range(MAX_BYE_IMPROVEMENT_ATTEMPTS):
        if _bye_key(best_bye, players)[0] <= best_possible_score:
            break  # [C5] beweisbar nicht mehr verbesserbar
        retry = _solve_round_both_passes(groups, players, topscorer_threshold, excluded)
        if retry is None:
            break  # keine echte Alternative mehr - bisher bestes Ergebnis behalten
        retry_pairs, retry_bye = retry
        if retry_bye is None:
            break  # sollte bei gleicher Teilnehmerzahl nicht vorkommen - sicherheitshalber abbrechen
        excluded = excluded | {retry_bye}
        if _bye_key(retry_bye, players) < _bye_key(best_bye, players):
            best_pairs, best_bye = retry_pairs, retry_bye
    return best_pairs, best_bye


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
    max_possible_score = float(total_rounds) if total_rounds is not None else float(max(round_no - 1, 0))
    topscorer_threshold = max_possible_score / 2.0
    groups = _scoregroups(active_players)

    result = _solve_round_both_passes(groups, active_players, topscorer_threshold, frozenset())
    if result is None:
        result = _global_matching_fallback(active_players, topscorer_threshold)
    if result is None:
        raise NoValidPairingError("keine gültige Rundenpaarung gefunden (Art. 1.9.3)")
    raw_pairs, bye_rank = result
    if bye_rank is not None:
        raw_pairs, bye_rank = _improve_bye_assignment(groups, active_players, topscorer_threshold, raw_pairs, bye_rank)

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
