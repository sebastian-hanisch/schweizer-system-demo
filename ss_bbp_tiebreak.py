"""**NICHT in den Live-Pfad verdrahtet** (Stand 2026-09-29, siehe project_turnierplanung_dag_scoping.md) -
reines Forschungsmodul, in `ss_bracket.py`/`ss_engine.py` bewusst NICHT importiert/aufgerufen. Grund:
der eigentliche verbliebene Mismatch-Anteil erwies sich NICHT als Tie-Break-Problem (bbpPairings'
echte Wahl fehlte schlicht in `ss_bracket.py`s enumeriertem Kandidatensatz - ein Suchbreiten-Deckel-
Problem), sondern wurde durch großzügigeres Anheben von `MAX_ALTERNATIVES`/`MAX_PER_MDP_PERM`/
`MAX_PAIRABLE_MDP_SETS`/`MAX_RAW_ATTEMPTS` in `ss_bracket.py` gelöst (98,178→99,299 % Standard-,
92,0→97,243 % härtere Stichprobe) - GEMESSEN, mit diesem Modul komplett DEAKTIVIERT, exakt
gleiches Ergebnis wie mit ihm aktiv. Dieses Modul bleibt als dokumentierte, getestete Forschung
erhalten (acht real gefundene, gegen `bbpPairings.exe` verifizierte Bugs, siehe unten und Memory),
für einen möglichen künftigen Anlauf - aber es trägt aktuell NICHTS zur Übereinstimmungsrate bei.

**Nachmessung 2026-09-29 (neue Sitzung) - WARUM es nichts beiträgt, jetzt konkret verstanden**: `resolve_tie`
wurde probeweise fest verdrahtet (`ss_bracket.py`s `_yield_sorted` versucht es zuerst, fällt bei `None`
zurück) und gegen den aktuellen 99,509 %/97,494 %-Stand gemessen - Ergebnis: BYTE-IDENTISCHE Mismatch-Mengen,
0 von 6884 Aufrufen (Standardstichprobe) lieferten je ein Ergebnis (`STATS['resolved'] == 0`). Instrumentierung
der `_bail`-Gründe zeigte: 93 % (6413/6884) scheitern am `noncontiguous`-Wächter (`remainder[:remainder_pairs]`
entspricht nicht der tatsächlichen Menge bereits geschlossener Paare). Direkter Quellcode-Fund
(`dutch.cpp:1270-1334`): der ECHTE C++-Code hat DIESEN Wächter GAR NICHT - er nimmt den Positions-Schnitt
`remainder[:remainderPairs]` blind, ohne Rückversicherung. Testweise entfernt (rein positional wie im Original)
und ERNEUT gegen den echten Sweep gemessen: NETTO SCHLECHTER (99,229 %/96,842 % statt 99,509 %/97,494 %) -
nicht besser. Der Wächter ist also trotz fehlendem C++-Vorbild empirisch nötig, was zeigt: das eigentliche
Problem liegt NICHT im `remainder`-Positions-Schnitt selbst, sondern TIEFER - `dutch.cpp:1091-1255` (vor dem
hier portierten `remainder`-Mechanismus) berechnet über denselben, INKREMENTELL über die GESAMTE
Bracket-Sequenz weitergereichten `matchingComputer` erst, WELCHE MDPs überhaupt wie gepaart werden
("Choose the moved down players" / "Choose the opponents of the moved down players") - dieser Teil ist hier
NICHT portiert; `resolve_tie` nimmt stattdessen `tied[0]` (unser EIGENES, unabhängig generiertes bestes
Ergebnis) direkt als Baseline. Für die meisten Fälle liefert das dieselbe Paarung wie bbpPairings' eigener
inkrementeller Prozess - aber die `remainder`-Positionsarithmetik ist gegen DESSEN spezifischen internen
Zustand kalibriert, nicht gegen eine unabhängig hergeleitete Baseline, und divergiert deshalb genau in den
Fällen, in denen es zählen würde. Das ist eine strukturelle Lücke (ein EINZELNES, inkrementell fortgeführtes
Matching-Objekt über die GANZE Paarungssequenz vs. unsere bracket-für-bracket-rekursive Suche mit spät
aufgesetztem Zwei-Bracket-Tie-Break) - kein Arithmetik-Bug, der sich durch weiteres Nachjustieren schließen
ließe. Schließen würde nur eine vollständige Neuimplementierung von bbpPairings' eigenem Matching-Ansatz
verlangen - genau der Ansatz, den dieses Repo bewusst zugunsten der wörtlichen Regeltext-Treue verworfen hat
(siehe `ss_bracket.py`s Moduldoku). Reales Fazit: 99,509 %/97,494 % ist mit dieser Architektur der praktisch
erreichbare Stand; weitere Versuche in diese Richtung ohne einen fundamental anderen Ansatz sind nicht
aussichtsreich.

Ursprünglicher Zweck (Beschreibung des Mechanismus, unverändert gültig): Portierung von
bbpPairings' iterativem gewichteten Matching-Tie-Break (dutch.cpp, gelesen aus dem geklonten
Quellcode) - sollte NUR aufgerufen werden, wenn `ss_bracket.py`s eigene, vollständige Suche
mehrere EXAKT gleich bewertete Kandidaten liefert (gleiche Downfloater-Anzahl, gleiche
Downfloater-Scores, gleiches C10-C21-Qualitätstupel). `resolve_tie` wählt IMMER nur unter genau
diesen bereits validierten (C1-C4-konformen) Kandidaten aus - erfindet nie eine neue Paarung.

**Scope (bewusst, siehe Plan)**: nur heterogene Brackets, aktuelle + unmittelbar nächste Bracket
(deckt sich mit bbpPairings' eigenem Zwei-Bracket-Scope, dutch.cpp:1087 "current+next combined").
MDPs floaten in diesem Modul NICHT weiter in die nächste Bracket (das wäre eine DRITTE Bracket-Ebene,
außerhalb des hier abgedeckten Scopes).

**Warum ein frisches Solve statt bbpPairings' inkrementellem Warmstart**: `matching::Computer`
(computer.h:16-22) unterstützt inkrementelle Updates (`O(k*n^2)` statt `O(n^3)` je Neulösen) - das ist
eine reine C++-Performance-Optimierung, keine Korrektheitsanforderung. Bracket-/Restgrößen hier sind
klein genug, dass ein kompletter Neu-Solve je Schritt über `networkx.max_weight_matching` unproblematisch
schnell bleibt.

**Warum kein Bit-Packing**: `computeEdgeWeight` (dutch.cpp:230-482) presst alle Kriterien in EIN
Integer mit FESTER Bit-Breite (C++-Notwendigkeit). Python-`int` ist beliebig groß - dieselbe
Prioritäts-Reihenfolge wird hier über gemischt-radix-Kodierung (`_pack`) erreicht, ohne
Bit-Breiten-Buchhaltung.

Volle Chronologie der acht gefundenen Bugs (MDP-Kaskade nicht erkannt, additive Canonical-Bias-Formel
strukturell ungeeignet für eine über die GESAMTE Paarung lexikografische Präferenz, uneinheitliche
Kantenskalierung zwischen Rest- und Nicht-Rest-Kanten, ...) sowie der Sweep-für-Sweep-Verlauf: siehe
project_turnierplanung_dag_scoping.md - hier absichtlich nicht dupliziert."""

from __future__ import annotations

from typing import TYPE_CHECKING, Iterable

import networkx as nx

from ss_compat import compatible
from ss_model import Player
from ss_quality import colour_terms, downfloat_repeat_terms, upfloat_repeat_terms

if TYPE_CHECKING:
    from ss_bracket import BracketContext, Candidate

# Temporäre Instrumentierung (Plan, Phase 5c) - NICHT dauerhaft gedacht, nur für die Verifikations-
# Sweeps dieser Sitzung: wie oft wird `resolve_tie` überhaupt aufgerufen (= echter Gleichstand
# gefunden), wie oft liefert es ein Ergebnis (vs. `None`-Fallback), wie oft weicht die Wahl vom
# bisherigen `_exchange_cost`-Favoriten (Position 0 vor der Umsortierung) ab.
STATS = {"calls": 0, "resolved": 0, "changed_vs_exchange_cost": 0, "bail": {}}


def _bail(reason: str) -> None:
    STATS["bail"][reason] = STATS["bail"].get(reason, 0) + 1

# Gemischt-radix-Feldliste, IMMER in dieser festen Reihenfolge/Länge befüllt (auch wenn ein
# Kriterium für eine bestimmte Kante gar nicht zutrifft - dann mit seinem NEUTRALEN/besten Wert
# aufgefüllt). Das ist entscheidend: eine variable Feldlänge je Kantentyp würde die beabsichtigte
# strikte Prioritäts-Dominanz brechen (eine kürzere, "schlechtere" Kategorie könnte sonst rein durch
# ihre andere Stellenanzahl numerisch über einer eigentlich höher priorisierten Kategorie landen -
# beim ersten Entwurf dieses Moduls tatsächlich per Handrechnung so gefunden und hier bewusst
# vermieden). Reihenfolge = Priorität, höchste zuerst:
#   1. innerhalb der AKTUELLEN Bracket (Residenten+MDPs) gepaart      -> [C6]-Analogon
#   2. innerhalb der NÄCHSTEN Bracket gepaart                        -> grobe Zweitpriorität
#      (dutch.cpp behandelt die nächste Bracket ebenfalls nur grob - unsere eigene Rekursion löst sie
#      danach ohnehin exakt selbst, siehe `ss_engine.py`)
#   3-6. C10, C11, C12, C13 (Farbe, invertiert: kleiner Rohwert = besser = GRÖSSERER Feldwert)
#   7-8. C15, C17 (Upfloat-Wiederholung des Residenten bei einer Resident-MDP-Kante, invertiert)
#   9-10. C14, C16 (Downfloat-Wiederholung des aktuellen-Bracket-Spielers bei einer Downfloat-Kante,
#         invertiert)
_RADICES = (2, 2, 3, 3, 3, 3, 2, 2, 2, 2)
_NEUTRAL = (0, 0, 2, 2, 2, 2, 1, 1, 1, 1)  # bester Wert je Feld, wenn ein Kriterium nicht zutrifft
_TIEBREAK_ROOM = 5  # reservierter Spielraum am unteren Ende, für Schritt 4-6 (Exchange-Anpassung um
# ganzzahlige Einheiten je Kandidat) - analog zu dutch.cpp:1055-1085s "addend <<= 1"-Reserve, hier
# großzügiger bemessen, da kein Bit-Breiten-Druck besteht. Startwert mittig, damit +/-1 in beide
# Richtungen sicher im reservierten Bereich bleibt, ohne in ein Nachbarfeld überzulaufen.
_TIEBREAK_NEUTRAL = _TIEBREAK_ROOM // 2


def _pack(fields: tuple[int, ...]) -> int:
    """Mischt `fields` (feste Reihenfolge/Länge, siehe `_RADICES`) gemischt-radix zu EINEM int."""
    result = 0
    for value, radix in zip(fields, _RADICES):
        assert 0 <= value < radix, (value, radix)
        result = result * radix + value
    return result * _TIEBREAK_ROOM + _TIEBREAK_NEUTRAL


def edge_weight(
    a: int,
    b: int,
    players: dict[int, Player],
    topscorer_threshold: float,
    current_pool: frozenset[int],
    mdp_ranks: frozenset[int],
) -> int | None:
    """Kantengewicht für (a, b) im kombinierten Pool (aktuelle Bracket + nächste Bracket) -
    Entsprechung zu `computeEdgeWeight` (dutch.cpp:230-482). `None` = keine Kante (C1/C3, via
    `ss_compat.compatible`)."""
    pa, pb = players[a], players[b]
    if not compatible(pa, pb, topscorer_threshold):
        return None

    both_current = a in current_pool and b in current_pool
    both_next = (a not in current_pool) and (b not in current_pool)
    fields = [int(both_current), int(both_next)]

    if both_current:
        c10, c11, c12, c13 = colour_terms(pa, pb, topscorer_threshold)
        fields += [2 - c10, 2 - c11, 2 - c12, 2 - c13]

        a_is_mdp, b_is_mdp = a in mdp_ranks, b in mdp_ranks
        if a_is_mdp != b_is_mdp:  # genau einer ist MDP -> der andere bekommt einen Upfloat (C15/C17)
            resident = b if a_is_mdp else a
            f15, f17 = upfloat_repeat_terms(players[resident])
            fields += [1 - f15, 1 - f17]
        else:
            fields += [_NEUTRAL[6], _NEUTRAL[7]]
        fields += [_NEUTRAL[8], _NEUTRAL[9]]
    elif both_next:
        fields += list(_NEUTRAL[2:])
    else:
        # Downfloat-Kante: genau ein Ende in der aktuellen, eins in der nächsten Bracket.
        fields += list(_NEUTRAL[2:6])
        current_side = a if a in current_pool else b
        if current_side in mdp_ranks:
            return None  # MDPs floaten hier nicht weiter (Zwei-Bracket-Scope, siehe Moduldoku)
        fields += [_NEUTRAL[6], _NEUTRAL[7]]
        f14, f16 = downfloat_repeat_terms(players[current_side])
        fields += [1 - f14, 1 - f16]

    return _pack(tuple(fields))


def _weighted_matching(pool: Iterable[int], weight_fn) -> dict[int, int]:
    """Baut bei JEDEM Aufruf einen frischen `networkx.Graph` (kein Warmstart - siehe Moduldoku) und
    löst das gewichtete allgemeine Matching OHNE erzwungene Maximalkardinalität
    (`maxcardinality=False`, networkx-Standard): die "möglichst viele Paare"-Präferenz steckt bereits
    als höchstprioritäres Feld IN den Gewichten selbst (wie bei bbpPairings' eigener Kodierung, die
    ebenfalls ein einfaches gewichtetes - kein kardinalitätsbeschränktes - Matching löst), nicht als
    separate Solver-Vorgabe. Knoten/Kanten werden in fester, aufsteigender Rang-Reihenfolge
    eingefügt, damit das Ergebnis bei mehreren gleich guten Optima reproduzierbar bleibt (networkx'
    eigenes internes Tie-Break-Verhalten ist nicht über Versionen hinweg garantiert stabil)."""
    ordered_pool = sorted(pool)
    graph = nx.Graph()
    graph.add_nodes_from(ordered_pool)
    for i, x in enumerate(ordered_pool):
        for y in ordered_pool[i + 1 :]:
            w = weight_fn(x, y)
            if w is not None:
                graph.add_edge(x, y, weight=w)

    mate_pairs = nx.max_weight_matching(graph, maxcardinality=False)
    mate: dict[int, int] = {}
    for x, y in mate_pairs:
        mate[x] = y
        mate[y] = x
    return mate


# --- Schritte 4-6: Exchange-Count + zwei geordnete gierige Scans -------------------------------
#
# Direkte Übersetzung aus dem gelesenen Quellcode (dutch.cpp:1257-1507, Zeilen im geklonten Repo
# unter scratchpad/bbp_source geprüft) - mit EINER bewussten Anpassung: bbpPairings reserviert für
# diesen Zusatzterm feste Bits INNERHALB derselben Kantengewicht-Variable (C++-Notwendigkeit, feste
# Wortbreite). Hier wird stattdessen ein SEPARATER, groß skalierter Zusatzterm auf das Basisgewicht
# addiert (`_remainder_weight`) - Python-`int` macht das unproblematisch, die Wirkung (Zusatzterm
# strikt UNTERHALB aller Basis-Kriterien, aber oberhalb von nichts weiterem) ist dieselbe.
#
# `remainder` = alle NICHT-MDP-Spieler des Pools (Residenten der aktuellen + der nächsten Bracket),
# in Art.-1.2-Reihenfolge (Score absteigend, dann Rang aufsteigend - das entspricht bbpPairings'
# global aufsteigender `vertexIndices`-Reihenfolge). `remainder_pairs` = Anzahl der im Baseline-
# Solve VOLLSTÄNDIG innerhalb `remainder` geschlossenen Paare; die ersten `remainder_pairs`
# Positionen bilden die "erste Gruppe" (typischerweise: Residenten, die im Baseline-Solve
# untereinander paarten), der Rest die "zweite Gruppe" (Downfloat-Kandidaten + nächste Bracket).


def _remainder_order(pool_without_mdps: Iterable[int], players: dict[int, Player]) -> list[int]:
    return sorted(pool_without_mdps, key=lambda r: (-players[r].score, r))


def _split_remainder(remainder: list[int], mate: dict[int, int]) -> tuple[int, list[int], list[int]]:
    """(remainder_pairs, first_group, second_group) - dutch.cpp:1257-1291."""
    position = {r: i for i, r in enumerate(remainder)}
    remainder_set = set(remainder)
    remainder_pairs = 0
    for r in remainder:
        partner = mate.get(r)
        if partner in remainder_set and position[partner] < position[r]:
            remainder_pairs += 1
    return remainder_pairs, remainder[:remainder_pairs], remainder[remainder_pairs:]


_REMAINDER_SCALE = 10**6  # so groß, dass der Zusatzterm (siehe unten) niemals das Basisgewicht
# verfälscht - Basisgewichte aus `edge_weight` bleiben bei den hier relevanten Bracket-/
# Restgrößen (Demo-Maßstab, siehe README) weit darunter.


def _remainder_weight(
    x: int,
    y: int,
    base_weight_fn,
    position: dict[int, int],
    remainder_pairs: int,
    perturbation: dict[tuple[int, int], int] | None = None,
) -> int | None:
    """`edgeWeightComputer` (dutch.cpp:1055-1085): Zusatzterm UNTERHALB des Basisgewichts, der
    Kanten bevorzugt, deren KLEINERER-Positions-Endpunkt selbst in der ersten Gruppe liegt
    (`smaller_pos < remainder_pairs`), darunter je nach Position abgestuft (frühere Position =
    leicht bevorzugt) - reiner Tie-Break zwischen sonst gleich guten Kanten. `perturbation` trägt
    die ±1-Anpassung der beiden gierigen Scans (dutch.cpp:1366/1439)."""
    base = base_weight_fn(x, y)
    if base is None:
        return None
    smaller, larger = (x, y) if position[x] < position[y] else (y, x)
    in_first_group = int(position[smaller] < remainder_pairs)
    addend = in_first_group * (len(position) + 1) - position[smaller]
    weight = base * _REMAINDER_SCALE + (len(position) + 1) + addend
    if perturbation:
        key = (smaller, larger)
        if key in perturbation:
            weight += perturbation[key]
    return weight


def _exchange_count(
    pool: list[int],
    base_weight_fn,
    remainder: list[int],
    remainder_pairs: int,
) -> tuple[int, dict[int, int]]:
    """dutch.cpp:1293-1334: EIN Neu-Solve mit dem `edgeWeightComputer`-Zusatzterm (ohne Störung)
    bestimmt, wie viele Mitglieder der ERSTEN Gruppe nach diesem Solve NICHT mehr regulär
    "vorwärts" innerhalb `remainder` gepaart sind - das wird zur festen Zielzahl für die beiden
    folgenden Scans. Gibt (Zielzahl, resultierendes Matching) zurück."""
    position = {r: i for i, r in enumerate(remainder)}

    def weight_fn(x: int, y: int):
        both_in_remainder = x in position and y in position
        if not both_in_remainder:
            base = base_weight_fn(x, y)
            # DIESELBE Skalierung wie `_remainder_weight` (sonst wiegen Kanten außerhalb von
            # `remainder`, z. B. zu einem MDP, im Vergleich zu remainder-Kanten künstlich viel zu
            # WENIG - der Solver würde dann eher einen MDP unversorgt lassen als eine der massiv
            # aufgewerteten remainder-Kanten zu opfern. Realer, gegen `bbpPairings.exe` gefundener
            # Regressionsfund dieser Sitzung: einheitliche Skala über den GANZEN Graphen ist Pflicht.
            return None if base is None else base * _REMAINDER_SCALE
        return _remainder_weight(x, y, base_weight_fn, position, remainder_pairs)

    mate = _weighted_matching(pool, weight_fn)

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
    *,
    target: int,
    scan_first_group: bool,
) -> dict[int, int]:
    """Scan 1 (`scan_first_group=True`, dutch.cpp:1339-1405): rückwärts durch die erste Gruppe
    (schlechteste/späteste Priorität zuerst) - je Kandidat werden testweise ALLE Kanten zu später
    liegenden `remainder`-Mitgliedern um 1 abgeschwächt und neu gelöst; pairt der Kandidat danach
    NICHT mehr normal vorwärts, gilt er als "ausgetauscht" (dauerhaft gesperrt gegen alle späteren
    Partner), sonst werden die Originalgewichte wiederhergestellt. Scan 2 (`scan_first_group=False`,
    dutch.cpp:1410-1507): spiegelbildlich vorwärts durch die zweite Gruppe, Kanten zu FRÜHEREN
    Partnern um 1 verstärkt statt abgeschwächt. Beide Scans laufen, bis `target` Austausche
    bestätigt sind oder die jeweilige Gruppe erschöpft ist - fester, sequenzieller Durchlauf, kein
    Batch-Vergleich."""
    position = {r: i for i, r in enumerate(remainder)}
    locked: set[tuple[int, int]] = set()  # dauerhaft auf 0 gesperrte Kanten (baseEdgeWeights &= 0u)

    def base_or_locked(x: int, y: int):
        key = (x, y) if x < y else (y, x)
        if key in locked:
            return None
        return base_weight_fn(x, y)

    def weight_fn(x: int, y: int):
        both_in_remainder = x in position and y in position
        if not both_in_remainder:
            base = base_or_locked(x, y)
            return None if base is None else base * _REMAINDER_SCALE  # einheitliche Skala, s. `_exchange_count`
        return _remainder_weight(x, y, base_or_locked, position, remainder_pairs)

    remaining = target
    sequence = list(reversed(remainder[:remainder_pairs])) if scan_first_group else remainder[remainder_pairs:]

    for player in sequence:
        if remaining <= 0:
            break
        pos_player = position[player]
        partner = mate.get(player)
        currently_forward = partner is not None and position.get(partner, -1) > pos_player
        already_exchanged = partner is not None and position.get(partner, -1) < pos_player  # nur Scan 2 relevant

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
                if w is not None:
                    perturbation[key] = nudge

            def perturbed_weight_fn(x: int, y: int, _pert=perturbation):
                both_in_remainder = x in position and y in position
                if not both_in_remainder:
                    base = base_or_locked(x, y)
                    return None if base is None else base * _REMAINDER_SCALE  # einheitliche Skala
                return _remainder_weight(x, y, base_or_locked, position, remainder_pairs, _pert)

            mate = _weighted_matching(pool, perturbed_weight_fn)

        new_partner = mate.get(player)
        new_pos = position.get(new_partner, -1) if new_partner is not None else -1
        if scan_first_group:
            exchanged = new_partner is None or new_pos <= pos_player
        else:
            exchanged = new_partner is not None and pos_player < new_pos < remainder_pairs

        if exchanged:
            remaining -= 1
            for opp in candidates_to_nudge:
                key = (player, opp) if player < opp else (opp, player)
                locked.add(key)

        mate = _weighted_matching(pool, weight_fn)  # Originalgewichte (abzüglich neuer Sperren)

    return mate


# --- Schritt 3 (Plan): Einstiegspunkt -----------------------------------------------------------


def resolve_tie(
    tied: "list[Candidate]",
    residents: list[int],
    mdps: list[int],
    next_group_residents: list[int],
    ctx: "BracketContext",
) -> "Candidate | None":
    """Wählt EINEN Kandidaten aus `tied` (>= 2, alle mit identischem (Downfloater-Anzahl,
    Downfloater-Scores, Qualitätstupel)) - NIE einen neu erfundenen. `None`, wenn der Mechanismus
    nicht anwendbar ist oder das per Matching gefundene Ergebnis KEINEM `tied`-Kandidaten entspricht
    (z. B. weil `ss_bracket.py`s eigene Enumerationsdeckel bbpPairings' echte Wahl gar nicht erst
    enumeriert haben - eine separate, legitime Grenze, kein Fehler dieses Moduls, siehe Moduldoku).
    Der Aufrufer fällt bei `None` auf die bestehende `_exchange_cost`-Heuristik zurück.

    **SECHSTER und siebter real gefundener Fund, die zu dieser Fassung führten** (Details in
    project_turnierplanung_dag_scoping.md): ein FRISCH via `_with_canonical_bias` gewichtetes
    Baseline-Solve (frühere Fassung) reproduziert bbpPairings' eigene, bereits als korrekt
    verifizierte Art.-4.2/4.3-Generierungsreihenfolge (`tied[0]`, der bisherige `_exchange_cost`-
    Favorit) NICHT zuverlässig - mehrere unabhängige Bias-Varianten (additiv, Stellenwert-kodiert,
    S1-vs-S2-bewusst) wurden gegen den echten Sweep gemessen, KEINE erreichte auch nur die
    bisherige Basis (98,178 %). Stattdessen wird HIER `tied[0]` (bereits nachweislich meist
    korrekt) direkt als Baseline verwendet - der Matching-Mechanismus (`_exchange_count`/
    `_greedy_scan`) wird NUR noch als zusätzliche Prüfung/Korrektur DARAUF angewendet, nicht als
    unabhängige Neuherleitung. Das brachte den Sweep von 96,987 % auf 98,108 % (fast Parität, nur
    noch 1 bekannter Restfall). ZUSÄTZLICH musste `remainder` explizit Residenten ausschließen, die
    bereits mit einem MDP gepaart sind (dutch.cpp:1276-1279s eigener Filter
    `stableMatching[playerVertex] < scoreGroupBeginVertex -> skip`) - ohne diesen Ausschluss
    verzerrte ein MDP-gepaarter Resident die Bestimmung von `remainder_pairs` fundamental.

    **Bekannte, noch offene Grenze** (nicht weiter geschlossen, Zeitbudget dieser Sitzung
    erschöpft): wenn `remainder` MEHR als ein unabhängiges, bereits geschlossenes Residenten-Paar
    enthält (nicht nur das eine Grenz-Paar an der m1-Schwelle), kann `_exchange_count`s
    Positions-basierte Zielzahl-Bestimmung fälschlich ein Austausch-Bedürfnis erkennen, wo keins
    besteht - ein konkreter, dokumentierter Regressionsfall dafür ist in
    project_turnierplanung_dag_scoping.md festgehalten. Der `contiguous`-Check unten fängt einen
    Teil dieser Fälle ab, aber nicht alle."""
    if not next_group_residents:
        return None
    STATS["calls"] += 1

    players = ctx.players
    pool = list(residents) + list(mdps) + list(next_group_residents)
    current_pool = frozenset(residents) | frozenset(mdps)
    mdp_ranks = frozenset(mdps)

    def base_weight_fn(x: int, y: int):
        return edge_weight(x, y, players, ctx.topscorer_threshold, current_pool, mdp_ranks)

    best = tied[0]
    baseline_mate: dict[int, int] = {}
    for a, b in best.pairs:
        baseline_mate[a] = b
        baseline_mate[b] = a

    if any(m not in baseline_mate for m in mdps):
        # Ein MDP bleibt unversorgt (ist unter `best.downfloaters`): die eigene Bracket reicht
        # nicht aus, um ihn unterzubringen - er müsste (außerhalb des Zwei-Bracket-Scopes dieses
        # Moduls, siehe Moduldoku) NOCH WEITER in eine übernächste Bracket floaten. Sauber auf
        # `None` zurückfallen statt eine verfälschte Restgruppen-Paarung zu erzwingen.
        _bail("mdp_unserved")
        return None

    # Residenten, die bereits mit einem MDP gepaart sind, gehören NICHT in `remainder`
    # (dutch.cpp:1276-1279: "stableMatching[playerVertex] < scoreGroupBeginVertex -> skip") -
    # ohne diesen Ausschluss verzerrt ein MDP-gepaarter Resident `remainder_pairs` (realer,
    # gegen `bbpPairings.exe` gefundener Regressionsfund dieser Sitzung).
    remainder_pool = [r for r in residents if baseline_mate.get(r) not in mdp_ranks] + list(next_group_residents)
    remainder = _remainder_order(remainder_pool, players)
    remainder_pairs, first_group, _second_group = _split_remainder(remainder, baseline_mate)
    if remainder_pairs == 0 or remainder_pairs == len(remainder):
        _bail("no_split")
        return None  # keine echte Aufteilung zwischen "erster" und "zweiter" Gruppe möglich
    # `remainder[:remainder_pairs]` (= `first_group`) MUSS GENAU der Menge aller innerhalb von
    # `remainder` bereits geschlossenen Paare entsprechen - nicht nur in sich selbst konsistent
    # sein (ein schwächerer, zuerst versuchter Test). ACHTER real gefundener Fund: enthält
    # `remainder` MEHR als EIN unabhängiges geschlossenes Paar (z. B. Residenten 4-7 UND 10-13,
    # mit einem dritten, noch ungepaarten Residenten dazwischen), bricht die Positions-basierte
    # "vorne abschneiden"-Annahme aus `_split_remainder`/dutch.cpp - dieser Fall ist (Stand dieser
    # Sitzung) NICHT zuverlässig lösbar, siehe "Bekannte, offene Grenze" oben. Sauber auf `None`
    # zurückfallen ist hier die einzig verifiziert sichere Wahl (gemessen: 98,178 % - exakte
    # Parität mit der bisherigen `_exchange_cost`-Basis, siehe project_turnierplanung_dag_scoping.md).
    remainder_set = set(remainder)
    all_paired_within_remainder = {r for r in remainder if baseline_mate.get(r) in remainder_set}
    if set(first_group) != all_paired_within_remainder:
        _bail("noncontiguous")
        return None

    target, mate_after_count = _exchange_count(pool, base_weight_fn, remainder, remainder_pairs)
    if target == 0:
        final_mate = baseline_mate  # kein Austausch nötig - `tied[0]`s eigene Paarung bleibt bestehen
    else:
        mate_after_scan1 = _greedy_scan(
            pool, base_weight_fn, remainder, remainder_pairs, mate_after_count,
            target=target, scan_first_group=True,
        )
        final_mate = _greedy_scan(
            pool, base_weight_fn, remainder, remainder_pairs, mate_after_scan1,
            target=target, scan_first_group=False,
        )

    inferred_downfloaters = frozenset(
        r for r in residents if r not in mdp_ranks and final_mate.get(r) not in current_pool
    )
    for candidate in tied:
        candidate_resident_downfloaters = frozenset(r for r in candidate.downfloaters if r not in mdp_ranks)
        if candidate_resident_downfloaters == inferred_downfloaters:
            STATS["resolved"] += 1
            return candidate
    _bail("no_tied_match")
    return None
