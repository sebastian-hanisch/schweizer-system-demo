"""Bracket-für-Bracket-Paarungssuche, WÖRTLICH nach dem FIDE-Regeltext (Art. 3 "Pairing Process
for a Bracket" + Art. 4 "Rules for the Sequential Generation of the Pairings",
handbook.fide.com/chapter/C0403202602) - Transposition (Art. 4.2) und Tausch/Exchange (Art. 4.3),
NICHT eine Neuformulierung als globales gewichtetes Matching (das war ein früherer, inzwischen
verworfener Ansatz, der sich an bbpPairings' eigener C++-Implementierungsstrategie orientierte,
nicht am Regeltext selbst - siehe project_turnierplanung_dag_scoping.md für die Begründung).

**Ablauf (Art. 3.3-3.8)**: pro Bracket wird zuerst die "natürliche" S1-gegen-S2-Paarung gebildet
(Art. 3.3.1: erster von S1 mit erstem von S2 usw. - das ist wörtlich die Konstruktion, aus der die
frühere "Canonical-Partner"-Regel empirisch abgeleitet werden musste; hier folgt sie direkt aus dem
Text). Erfüllt dieser Kandidat NICHT alle Kriterien C10-C17 ("perfekt", Art. 3.4.1), werden
Transpositionen von S2 durchprobiert (Art. 4.2, lexikografische Reihenfolge), danach - falls immer
noch kein perfekter Kandidat - Tausche zwischen S1 und S2 (Art. 4.3), je mit vollständiger
Transpositions-Unterprobe.

**Echtes Backtracking statt Heuristik**: `solve_bracket` gibt nicht mehr NUR den lokal besten
Kandidaten zurück, sondern (verzögert/lazy) ALLE brauchbaren Kandidaten in Prioritätsreihenfolge
(Art. 3.8.1). `ss_engine.py` versucht für jeden tatsächlich, die RESTLICHE Runde damit zu Ende zu
lösen (echte Rekursion) - erst wenn das fehlschlägt, wird der nächste Kandidat (bzw. bei Erschöpfung
eine kleinere Paarzahl) probiert. Das ersetzt eine frühere, nur ungefähre Existenz-Heuristik
([C4]/[C8] per einzelnem Kardinalitäts-Matching geschätzt statt tatsächlich nachgeprüft), die beim
dutch_2025_C5-Fixturenabgleich einen echten Fund lieferte (siehe project_turnierplanung_dag_scoping.md):
ein Kandidat mit lokal WENIGER Downfloatern kann eine SPÄTERE Bracket zwingen, ihr eigenes
strukturelles Maximum zu unterschreiten - der Regeltext selbst löst das nicht durch eine lokale
Heuristik, sondern schlicht dadurch, dass ein solcher Kandidat gar nicht erst "funktioniert", wenn
man die Runde tatsächlich zu Ende löst.

**Sicherheitsgrenzen** (zwei getrennte, bewusst KLEINE Deckel, keine geht auf Kosten der
Korrektheit): `MAX_RAW_ATTEMPTS` begrenzt, wie viele rohe Transpositionen/Tausche je S1/S2-Aufteilung
höchstens durchprobiert werden, um GENUG gültige (C1/C3-konforme) Kandidaten zu finden;
`MAX_ALTERNATIVES` begrenzt, wie viele davon je Aufteilung gesammelt/sortiert werden, bevor die
Suche weitergeht. Beide greifen bei realistischer Turniergröße praktisch nie (siehe README) - ein
letzter Rettungsanker (`_matching_fallback`, eine reine bipartite Kardinalitäts-Paarung) garantiert
zusätzlich, dass die Existenzgarantie [C4] selbst im pathologischen Fall nie verletzt wird."""

from __future__ import annotations

from dataclasses import dataclass
from itertools import combinations, permutations
from typing import Iterator

from ss_blossom import maximum_cardinality_matching
from ss_compat import compatible
from ss_model import Player
from ss_quality import colour_terms, downfloat_repeat_terms, upfloat_repeat_terms

MAX_RAW_ATTEMPTS = 20_000
MAX_ALTERNATIVES = 30
MAX_PER_MDP_PERM = 3  # je MDP-Paarungs-Wahl höchstens so viele Restgruppen-Kandidaten sammeln, sonst
# könnte EINE mdp_perm-Wahl mit vielen fast gleich guten Restgruppen-Varianten das ganze
# MAX_ALTERNATIVES-Budget füllen, bevor überhaupt eine ANDERE (farblich ggf. bessere) mdp_perm-Wahl
# versucht wird - realer Regressionsfund, siehe project_turnierplanung_dag_scoping.md
MAX_PAIRABLE_MDP_SETS = 20  # je m1-Stufe höchstens so viele TATSÄCHLICH kompatible MDP-Mengen
# (aus `_mdp_pairable_sets`) durchprobieren - bei vielen MDPs kann `combinations(mdps, m1)` sehr
# groß werden; die kanonische Menge zuerst plus großzügig viele Alternativen reicht, um [C7] gut
# abzudecken, ohne bei großen Feldern spürbar langsam zu werden (realer Regressionsfund)


class NoValidPairingError(Exception):
    """Für diese Runde existiert keine Paarung, die Art. 2.2.1 [C4] erfüllt (z. B. weil unter den
    verbliebenen Spielern jedes mögliche Paar schon einmal gegeneinander gespielt hat) - der
    Regeltext selbst behandelt das als Fall für den Turnierleiter (Art. 1.9.3), kein Programmfehler."""


@dataclass(frozen=True)
class Candidate:
    pairs: tuple[tuple[int, int], ...]  # (rang_a, rang_b) je Paarung, Farbe noch offen
    downfloaters: tuple[int, ...]  # residente (+ Limbo-)Ränge, die aus DIESER Bracket herausfallen


@dataclass
class BracketContext:
    players: dict[int, Player]
    topscorer_threshold: float


def _exchange_splits(s1: tuple[int, ...], s2: tuple[int, ...]) -> Iterator[tuple[tuple[int, ...], tuple[int, ...]]]:
    """Art. 4.3: erst der unveränderte Original-Split (kein Tausch), dann alle Tausche gleich
    großer Gruppen zwischen S1 und S2, sortiert nach den vier Vergleichsregeln (4.3.2)."""
    yield s1, s2
    max_k = min(len(s1), len(s2))
    for k in range(1, max_k + 1):
        exchanges = []
        for a_group in combinations(s1, k):  # von S1 nach S2 bewegt
            for b_group in combinations(s2, k):  # von S2 nach S1 bewegt
                sum_diff = abs(sum(b_group) - sum(a_group))
                # Regel 3: größte differierende BSN (S1->S2) gewinnt -> absteigend sortiert, negiert
                # (damit ascending-Tupelvergleich "besser zuerst" ergibt). Regel 4: kleinste
                # differierende BSN (S2->S1) gewinnt -> aufsteigend sortiert, unverändert.
                key = (sum_diff, tuple(-x for x in sorted(a_group, reverse=True)), tuple(sorted(b_group)))
                exchanges.append((key, a_group, b_group))
        exchanges.sort(key=lambda t: t[0])
        for _, a_group, b_group in exchanges:
            new_s1 = tuple(sorted((set(s1) - set(a_group)) | set(b_group)))
            new_s2 = tuple(sorted((set(s2) - set(b_group)) | set(a_group)))
            yield new_s1, new_s2


def _transpositions(s2: tuple[int, ...], n1: int) -> Iterator[tuple[int, ...]]:
    """Art. 4.2: alle geordneten Auswahlen der ersten N1 BSNs von S2, lexikografisch sortiert.
    `itertools.permutations` liefert das bereits in dieser Reihenfolge bei sortierter Eingabe."""
    yield from permutations(sorted(s2), n1)


def _quality_tuple(
    pairs: list[tuple[int, int]],
    resident_downfloaters: list[int],
    mdp_ranks: frozenset[int],
    players: dict[int, Player],
    topscorer_threshold: float,
) -> tuple:
    """(C10, C11, C12, C13, C14, C15, C16, C17, C18, C19, C20, C21) - je kleiner, desto besser;
    direkter Tupel-Vergleich (kein Basis-/Radix-Trick nötig). [C8] ("nächste Bracket erfüllt C1-C7")
    ist HIER absichtlich NICHT mehr enthalten - das entscheidet jetzt `ss_engine.py` direkt, indem es
    die Runde mit diesem Kandidaten tatsächlich zu Ende löst, statt es lokal zu schätzen."""
    c10 = c11 = c12 = c13 = 0
    for a, b in pairs:
        t10, t11, t12, t13 = colour_terms(players[a], players[b], topscorer_threshold)
        c10 += t10
        c11 += t11
        c12 += t12
        c13 += t13

    c14 = c16 = 0
    flagged_14, flagged_16 = [], []
    for r in resident_downfloaters:
        f14, f16 = downfloat_repeat_terms(players[r])
        c14 += f14
        c16 += f16
        if f14:
            flagged_14.append(players[r].score)
        if f16:
            flagged_16.append(players[r].score)

    c15 = c17 = 0
    flagged_15, flagged_17 = [], []
    for a, b in pairs:
        resident = a if b in mdp_ranks else (b if a in mdp_ranks else None)
        if resident is None:
            continue
        f15, f17 = upfloat_repeat_terms(players[resident])
        c15 += f15
        c17 += f17
        if f15:
            flagged_15.append(players[resident].score)
        if f17:
            flagged_17.append(players[resident].score)

    c18 = tuple(sorted(flagged_14, reverse=True))
    c19 = tuple(sorted(flagged_15, reverse=True))
    c20 = tuple(sorted(flagged_16, reverse=True))
    c21 = tuple(sorted(flagged_17, reverse=True))

    return (c10, c11, c12, c13, c14, c15, c16, c17, c18, c19, c20, c21)


_PERFECT_PREFIX_LEN = 8  # C10..C17 müssen 0 sein für "perfekt"; C18-C21 sind dann automatisch leer


def _is_perfect(quality: tuple) -> bool:
    return all(v == 0 for v in quality[:_PERFECT_PREFIX_LEN])


def _search_at_fixed_size(
    s1: tuple[int, ...],
    s2: tuple[int, ...],
    fixed_pairs: list[tuple[int, int]],
    mdp_ranks: frozenset[int],
    ctx: BracketContext,
    extra_downfloaters: tuple[int, ...] = (),
) -> list[Candidate]:
    """Art. 3.6: Transposition/Tausch-Suche für EINE feste S1/S2-Aufteilung (fester Paarzahl).
    Sammelt bis zu `MAX_ALTERNATIVES` gültige Kandidaten (stabil nach Qualität sortiert - "generiert
    früher" gewinnt bei Gleichstand automatisch durch Python's stabilen Sort, Art. 3.8.1) für die
    aufrufende Rekursion, damit sie bei Bedarf mehr als nur den EINEN besten ausprobieren kann."""
    n1 = len(s1)
    collected: list[tuple[tuple, Candidate]] = []
    examined = 0

    for split_s1, split_s2 in _exchange_splits(s1, s2):
        for perm in _transpositions(split_s2, n1):
            examined += 1
            pairs = fixed_pairs + list(zip(split_s1, perm))
            downfloaters = sorted(set(split_s2) - set(perm))
            all_downfloaters = sorted(downfloaters + list(extra_downfloaters))

            if all(compatible(ctx.players[a], ctx.players[b], ctx.topscorer_threshold) for a, b in pairs):
                resident_downfloaters = [r for r in all_downfloaters if r not in mdp_ranks]
                quality = _quality_tuple(pairs, resident_downfloaters, mdp_ranks, ctx.players, ctx.topscorer_threshold)
                candidate = Candidate(pairs=tuple(pairs), downfloaters=tuple(all_downfloaters))
                collected.append((quality, candidate))
                if len(collected) >= MAX_ALTERNATIVES:
                    break
            if examined >= MAX_RAW_ATTEMPTS:
                break
        else:
            continue
        break

    if not collected:
        fallback = _matching_fallback(s1, s2, fixed_pairs, mdp_ranks, ctx, extra_downfloaters)
        return [fallback] if fallback is not None else []

    collected.sort(key=lambda t: t[0])  # stabil: Gleichstände behalten Generierungsreihenfolge
    return [c for _, c in collected]


def _matching_fallback(
    s1: tuple[int, ...],
    s2: tuple[int, ...],
    fixed_pairs: list[tuple[int, int]],
    mdp_ranks: frozenset[int],
    ctx: BracketContext,
    extra_downfloaters: tuple[int, ...],
) -> Candidate | None:
    """Letzter Rettungsanker, NUR wenn die Transposition/Tausch-Suche innerhalb ihres Rohbudgets
    (`MAX_RAW_ATTEMPTS`) KEINEN einzigen [C1]/[C3]-konformen Kandidaten gefunden hat: eine reine
    bipartite Kardinalitäts-Paarung zwischen S1 und S2, ohne Rücksicht auf die exakte
    Transpositions-Reihenfolge oder C10-C21-Feinheiten. Garantiert nur, dass [C4] nie fälschlich
    verletzt wird - nicht, dass das Ergebnis FIDE-qualitätsoptimal ist."""
    n1 = len(s1)
    if n1 == 0:
        downfloaters = sorted(set(s2) | set(extra_downfloaters))
        return Candidate(pairs=tuple(fixed_pairs), downfloaters=tuple(downfloaters))

    pool = list(s1) + list(s2)
    s1_set = set(s1)
    n = len(pool)
    adj: list[list[int]] = [[] for _ in range(n)]
    for i in range(n):
        for j in range(i + 1, n):
            if (pool[i] in s1_set) == (pool[j] in s1_set):
                continue  # nur S1-gegen-S2-Kanten (bipartit), wie Art. 3.3.1
            if compatible(ctx.players[pool[i]], ctx.players[pool[j]], ctx.topscorer_threshold):
                adj[i].append(j)
                adj[j].append(i)

    mate = maximum_cardinality_matching(n, adj)
    matched_s1 = {i for i in mate if pool[i] in s1_set}
    if len(matched_s1) != n1:
        return None  # keine vollständige S1-Zuordnung möglich - diese Paarzahl nicht erreichbar

    new_pairs = [(pool[i], pool[mate[i]]) for i in matched_s1]
    matched_players = {pool[i] for i in mate}
    downfloaters = sorted((set(s2) - matched_players) | set(extra_downfloaters))
    return Candidate(pairs=tuple(fixed_pairs + new_pairs), downfloaters=tuple(downfloaters))


def _search_homogeneous(
    residents: list[int],
    max_pairs: int,
    fixed_pairs: list[tuple[int, int]],
    mdp_ranks: frozenset[int],
    ctx: BracketContext,
    extra_downfloaters: tuple[int, ...] = (),
) -> Iterator[Candidate]:
    """Verzögert (lazy): versucht zuerst `max_pairs` Paare (Art. 3.1.2/3.2.2), und erst wenn die
    aufrufende Rekursion ALLE dort gefundenen Kandidaten erfolglos durchprobiert hat, schrittweise
    WENIGER - [C6] ("minimiere Downfloater") ist ein QUALITÄTS-, kein absolutes Kriterium, [C4]
    (Rundenvervollständigung) hat Vorrang. `extra_downfloaters` (Limbo, Art. 3.2.4) zählen immer mit."""
    for n1_attempt in range(max_pairs, -1, -1):
        s1 = tuple(residents[:n1_attempt])
        s2 = tuple(residents[n1_attempt:])
        yield from _search_at_fixed_size(s1, s2, fixed_pairs, mdp_ranks, ctx, extra_downfloaters)


def _mdp_pairable_sets(mdps: tuple[int, ...], m1: int, players: dict[int, Player]) -> Iterator[tuple[int, ...]]:
    """Art. 4.4: gültige Mengen paarbarer MDPs (Limbo = die übrigen). `mdps` ist bereits nach Art. 1.2
    sortiert (Score absteigend, dann Rang aufsteigend) - die KANONISCHE Menge (die ersten m1) wird
    zuerst versucht, danach alle anderen Größe-m1-Teilmengen in `itertools.combinations`-Reihenfolge
    (die für eine sortierte Eingabe zuerst systematisch die SPÄTESTEN Positionen ersetzt, also
    näher an der kanonischen Menge bleibt, bevor sie sich weiter davon entfernt).

    Frühere Fassung bot Alternativen NUR bei einem Score-GLEICHSTAND genau an der m1-Grenze an - ist
    die kanonische Top-m1-Menge dagegen strukturell (nicht gleichstandsbedingt) inkompatibel (z. B.
    weil der höchstbewertete MDP schon gegen den einzigen verbliebenen Residenten gespielt hat),
    gab es KEINEN Rückfall auf einen niedriger bewerteten MDP bei GLEICHER Größe m1 - die Suche
    sprang fälschlich direkt auf eine KLEINERE m1-Stufe, obwohl eine gültige, gleich große Menge
    existierte (realer, gegen `bbpPairings.exe` gefundener Regressionsfund - ohne diesen Rückfall
    landete die Rundenlösung im reinen Existenz-Fallback, der [C5] komplett ignoriert).

    Bei einem ECHTEN Score-Gleichstand innerhalb der m1-Grenze (C6/C7/C10-C21 unterscheiden dann
    nichts mehr) wurde experimentell geprüft, ob eine bestimmte Ausschluss-Reihenfolge (z. B. "der in
    Art.-1.2-Reihenfolge früheste MDP zuerst ausgeschlossen") bbpPairings' Wahl systematisch trifft -
    EIN von Hand nachvollzogener Fund passte, gegen eine größere Zufallsstichprobe gemessen aber
    NETTO SCHLECHTER als die kanonische Reihenfolge hier (97,8→97,5 % bzw. mehr Mismatches auf einer
    härteren Stichprobe) - verworfen. bbpPairings löst diesen Rest-Gleichstand nachweislich über ein
    mehrstufiges Neulösen mit gezielt angepassten Kantengewichten (Quellcode-Fund, s.
    project_turnierplanung_dag_scoping.md), nicht über eine einzelne statische Reihenfolge-Regel -
    dieser Rest ist ohne eine echte Portierung jenes iterativen Mechanismus nicht zuverlässig zu
    schließen."""
    if m1 >= len(mdps):
        yield mdps
        return
    if m1 <= 0:
        yield ()
        return
    yield from combinations(mdps, m1)


def solve_bracket(residents: list[int], mdps: list[int], ctx: BracketContext) -> Iterator[Candidate]:
    """Löst EINE Bracket (Art. 3.1-3.8): homogen, wenn `mdps` leer ist, sonst heterogen (MDP-Paarung
    + Restgruppe, Art. 3.3.3/3.7). Verzögert (lazy) ALLE brauchbaren Kandidaten in Prioritätsreihenfolge
    - die aufrufende Rekursion in `ss_engine.py` entscheidet per echtem Weiterlösen, welcher tragfähig
    ist (siehe Moduldoku). `mdps` muss NICHT vorsortiert sein - wird hier nach Art. 1.2 (Score
    absteigend, dann Rang aufsteigend) normalisiert: `Candidate.downfloaters` (die Quelle für `mdps`
    beim nächsten Aufruf) ist nur nach RANG sortiert, nicht nach Score - ohne diese Normalisierung
    würde `_mdp_pairable_sets`s [C7]-Tie-Break (niedrigst bewerteter MDP geht in die Limbo) bei
    unterschiedlich bewerteten MDPs genau VERKEHRT herum greifen (echter, gefundener Bug)."""
    mdps = sorted(mdps, key=lambda r: (-ctx.players[r].score, r))
    n_residents = len(residents)
    m0 = len(mdps)
    total = n_residents + m0
    max_pairs = min(total // 2, n_residents)
    structural_m1 = min(m0, max_pairs)

    if m0 == 0:
        yield from _search_homogeneous(residents, max_pairs, [], frozenset(), ctx)
        return

    # Art. 3.7: die MDP-Seite (S1) wird nur über Transposition der Resident-Seite (S2) variiert -
    # kein Tausch hier (Tausch gehört ausschließlich zur Restgruppe, Art. 3.7.1/3.6.1) - und über
    # den Wechsel der paarbaren MDP-Menge selbst (Art. 3.7.3, äußerste Schleife). Zusätzlich: `m1`
    # (Art. 3.1.3) wird rein strukturell (Score/Anzahl) bestimmt, OHNE Kompatibilität zu prüfen - ist
    # KEIN der `structural_m1` paarbaren MDPs mit IRGENDEINEM Residenten kompatibel (z. B. weil er
    # bereits gegen alle gespielt hat), muss m1 wie bei [C6] schrittweise reduziert werden (analog zu
    # `_search_homogeneous`s n1_attempt-Reduktion) - sonst bleibt diese Bracket fälschlich ohne
    # jeden Kandidaten (realer Regressionsfund, siehe project_turnierplanung_dag_scoping.md).
    #
    # WICHTIG: verschiedene mdp_perm-Wahlen erzeugen KEINE gleich guten Kandidaten (das MDP-Paar
    # selbst trägt zu C10-C21 bei, z. B. Farbkonflikt) - sie müssen deshalb über ALLE mdp_perm-Werte
    # hinweg nach Qualität verglichen werden, nicht nur INNERHALB eines festen mdp_perm (sonst würde
    # ein früh generierter, aber farblich schlechterer Kandidat einen später generierten, besseren
    # verdecken - realer Regressionsfund, siehe project_turnierplanung_dag_scoping.md).
    mdp_ranks = frozenset(mdps)
    examined = 0
    collected: list[tuple[tuple, Candidate]] = []

    # bbpPairings' eigener Quellcode (dutch.cpp, Fund via Quellcode-Lektüre, s.
    # project_turnierplanung_dag_scoping.md) zeigt: der verbleibende, durch C6/C7/C10-C21 NICHT
    # auflösbare Rest-Gleichstand (mehrere exakt gleich bewertete MDPs an der m1-Grenze) wird NICHT
    # über eine statische Regel entschieden, sondern über "minimiere die Anzahl nötiger Tausche
    # gegenüber der besten VOLLEN (m1=m0) Paarung, danach minimiere die BSN-Summe der dabei
    # aufgegebenen Paare". `baseline_pairs` ist genau diese beste volle Paarung (m1=structural_m1,
    # das erste/beste laut Art. 3.4.1-Priorität gefundene Ergebnis - unabhängig davon, ob sie später
    # rundenweit überhaupt durchlösbar ist, rein bracket-lokal wie bbpPairings' eigene "stabile"
    # Paarung). Zwei einfachere Heuristiken (kanonisch zuerst, umgekehrt zuerst) wurden VORHER gegen
    # eine große Zufallsstichprobe geprüft und beide als NETTO SCHLECHTER verworfen - dieser Ansatz
    # bildet das tatsächliche Kriterium nach, nicht nur eine plausibel klingende Reihenfolge.
    baseline_pairs: dict[int, int] = {}
    if structural_m1 > 0:
        for candidate in _search_at_fixed_size(
            tuple(mdps[:structural_m1]), tuple(residents), [], mdp_ranks, ctx
        ):
            baseline_pairs = {a: b for a, b in candidate.pairs if a in mdp_ranks}
            break

    def _exchange_cost(candidate_pairs: list[tuple[int, int]]) -> tuple[int, int]:
        """(Anzahl gegenüber `baseline_pairs` aufgegebener MDP-Paare, Summe ihrer BSNs) - beides zu
        minimieren, als letzter Tie-Break NACH C6/C7/C10-C21 (nur relevant, wenn die davor nichts
        mehr unterscheiden)."""
        paired_mdps = {a for a, _ in candidate_pairs if a in mdp_ranks}
        given_up = [(mdp, partner) for mdp, partner in baseline_pairs.items() if mdp not in paired_mdps]
        return len(given_up), sum(mdp + partner for mdp, partner in given_up)

    # Ein höheres m1 (mehr MDPs direkt eingebunden) erreicht NICHT automatisch weniger Downfloater
    # als ein niedrigeres - fehlt einem MDP bei kleinerem m1 der Platz, können die dadurch freien
    # Residenten stattdessen UNTEREINANDER paaren und so denselben Downfloater-Gesamtstand
    # erreichen. Bei GLEICHEM Downfloater-Stand entscheidet dann [C7] (Downfloater-Score
    # minimieren) - eine feste "höheres m1 zuerst, nie mit kleinerem verglichen"-Priorität würde
    # einen Kandidaten mit schlechterem [C7] (höher bewerteter Downfloater) fälschlich vor einem
    # mit besserem [C7] (aus kleinerem m1) ausgeben (realer, gegen bbpPairings.exe gefundener Fund).
    # Um dafür NICHT jedes Mal blind ALLE m1-Stufen erschöpfend durchzurechnen (das kostete bei
    # großen Feldern spürbar Zeit, obwohl die höchste Stufe fast immer schon reicht), wird nur dann
    # in DIESELBE Sammel-/Sortier-Charge weitergemacht, wenn die NÄCHSTKLEINERE Stufe strukturell
    # überhaupt noch denselben (oder besseren) Downfloater-Gesamtstand erreichen KÖNNTE (reine
    # Paaranzahl-Arithmetik, Art. 2.4.1/2.4.2) - sonst wird die bisherige Charge sofort ausgegeben
    # (lazy) und die nächste Stufe startet eine neue, unabhängige Charge.
    def _max_pairs_for(m1_value: int) -> int:
        return m1_value + (n_residents - m1_value) // 2

    for m1 in range(structural_m1, -1, -1):
        successful_mdp_pairings = 0
        for pairable_mdps in _mdp_pairable_sets(tuple(mdps), m1, ctx.players):
            if successful_mdp_pairings >= MAX_PAIRABLE_MDP_SETS:
                # Bei vielen MDPs kann `combinations(mdps, m1)` sehr groß werden (Regressionsfund:
                # 5+ MDPs mit mehreren möglichen m1-Größen ließen die Suche für einzelne Brackets
                # spürbar langsam werden) - sobald genug tatsächlich kompatible Mengen gefunden
                # wurden, um `collected` gut zu füllen, lohnt sich das Durchprobieren immer
                # entfernterer (und damit nach [C7] ohnehin unwahrscheinlich besserer) Restmengen
                # nicht mehr. Deckt die kanonische Menge plus großzügig viele Alternativen ab.
                break
            limbo = tuple(r for r in mdps if r not in pairable_mdps)

            found_compatible_perm = False
            for mdp_perm in _transpositions(tuple(residents), len(pairable_mdps)):
                examined += 1
                if examined > MAX_RAW_ATTEMPTS:
                    break
                mdp_pairs = list(zip(pairable_mdps, mdp_perm))
                if not all(compatible(ctx.players[a], ctx.players[b], ctx.topscorer_threshold) for a, b in mdp_pairs):
                    continue
                found_compatible_perm = True

                remainder_residents = sorted(set(residents) - set(mdp_perm))
                remainder_max_pairs = len(remainder_residents) // 2
                downfloater_tier_counts: dict[int, int] = {}
                for candidate in _search_homogeneous(
                    remainder_residents, remainder_max_pairs, mdp_pairs, mdp_ranks, ctx, extra_downfloaters=limbo
                ):
                    # [MAX_PER_MDP_PERM] begrenzt je DISTINKTER Downfloater-Anzahl-Stufe (nicht roh
                    # über alle Stufen hinweg) UND begrenzt die Anzahl verschiedener Stufen selbst:
                    # `_search_homogeneous` liefert erst ALLE Kandidaten der besten (wenigsten
                    # Downfloater) Stufe, bevor sie überhaupt reduziert - hätte diese oberste Stufe
                    # für sich allein schon >= MAX_PER_MDP_PERM Varianten (z. B. durch mehrere
                    # Tausch-Kombinationen), würde die Suche NIE zur nächst-schlechteren Stufe
                    # vordringen, selbst wenn genau DIE später rundenweit gebraucht wird (realer,
                    # gegen `bbpPairings.exe` gefundener Regressionsfund - die oberste Stufe kann
                    # bracket-lokal perfekt aussehen, aber die restliche Runde unlösbar machen).
                    n_downfloaters = len(candidate.downfloaters)
                    tier_count = downfloater_tier_counts.get(n_downfloaters, 0)
                    if tier_count >= MAX_PER_MDP_PERM:
                        continue  # diese Stufe ist voll - weitere (schlechtere) Stufen noch probieren
                    if tier_count == 0 and len(downfloater_tier_counts) >= MAX_PER_MDP_PERM:
                        break  # genug verschiedene Stufen schon gesehen
                    downfloater_tier_counts[n_downfloaters] = tier_count + 1
                    resident_downfloaters = [r for r in candidate.downfloaters if r not in mdp_ranks]
                    quality = _quality_tuple(list(candidate.pairs), resident_downfloaters, mdp_ranks, ctx.players, ctx.topscorer_threshold)
                    # [C6] zuerst (weniger Downfloater = besser), dann [C7] (Downfloater-Scores
                    # absteigend sortiert minimieren), erst danach C10-C21: verschiedene mdp_perm-
                    # Restgruppen können unterschiedlich viele Paare UND unterschiedlich hoch
                    # bewertete Downfloater erreichen, und ohne diesen Vorrang würde ein Kandidat mit
                    # MEHR/höher bewerteten Downfloatern, aber zufällig "besserer" Farbe, einen
                    # besseren verdecken (realer Regressionsfund).
                    downfloater_scores = tuple(sorted((ctx.players[r].score for r in candidate.downfloaters), reverse=True))
                    sort_key = (len(candidate.downfloaters), downfloater_scores, quality, _exchange_cost(list(candidate.pairs)))
                    collected.append((sort_key, candidate))
                    if len(collected) >= MAX_ALTERNATIVES:
                        break
                if len(collected) >= MAX_ALTERNATIVES:
                    break
            if found_compatible_perm:
                successful_mdp_pairings += 1
            if len(collected) >= MAX_ALTERNATIVES:
                break
        if len(collected) >= MAX_ALTERNATIVES or examined > MAX_RAW_ATTEMPTS:
            break

        if collected:
            best_downfloaters_so_far = min(len(c.downfloaters) for _, c in collected)
            next_min_downfloaters = n_residents + m0 - 2 * _max_pairs_for(m1 - 1) if m1 > 0 else n_residents + m0
            if next_min_downfloaters > best_downfloaters_so_far:
                collected.sort(key=lambda t: t[0])  # stabil: Gleichstände behalten Generierungsreihenfolge
                for _, candidate in collected:
                    yield candidate
                collected = []

    if collected:
        collected.sort(key=lambda t: t[0])
        for _, candidate in collected:
            yield candidate
