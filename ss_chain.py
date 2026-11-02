"""Rundenlösung in zwei Phasen: erst die KETTE der Downfloater-Mengen, dann die Paarungen.

Die Kriterien C5-C9 (Freilos, Zahl und Scores der Downfloater, [C8] "der folgende Block erfüllt C1-C7")
hängen nur davon ab, WER aus jedem Block herausfällt, nicht davon, wie der Rest des Blocks gepaart wird und
mit welchen Farben. Die Farb- und Float-Kriterien C10-C21 entscheiden danach, in dieser Reihenfolge, nur noch
unter den Paarungen, die zu derselben Downfloater-Menge führen.

**Phase 1 (`_Chain.best`)**: dynamische Programmierung über Zustände (Block k, hereinfallende Spieler). Je Zustand
werden die möglichen Mengen der aus diesem Block herausfallenden Spieler nach ([C6] Zahl, [C7] Scores absteigend)
sortiert und der Reihe nach geprüft: lässt sich der Rest des Blocks perfekt paaren (billiger Matching-Test, keine
Kandidatenliste), und wie gut wird dann der Rest der Runde (rekursiv, gemerkt)? Die erste ([C6]/[C7]-)Gruppe mit
mindestens einer tragfähigen Menge gewinnt, und darin die Mengen mit dem besten Rest-Profil - das ist [C8], über
die GANZE Restkette statt nur über den nächsten Block.

**Phase 2 (`_Chain.solve`)**: entlang der gewählten Kette wird je Block der Kandidatenstrom der Bracket-Suche
(`ss_bracket.solve_bracket`, sortiert nach C10-C21) gelesen, und der erste Kandidat, dessen Downfloater-Menge zu
den in Phase 1 besten gehört, gewinnt. Die Kandidatenliste mit ihrer Farbbewertung wird so nur einmal je Block
entlang des gewählten Wegs aufgebaut, nicht für jeden Zustand der Phase 1.

Das Freilos ([C5]: Score des Empfängers minimieren, dann [C9]) wird von außen als Obergrenze `bye_cap` für den
Schlüssel (Score, ungespielte Partien) des Empfängers eingestellt: die kleinste Obergrenze, bei der überhaupt
eine vollständige Runde existiert, gewinnt."""

from __future__ import annotations

from itertools import combinations, groupby

from ss_bracket import BracketContext, Candidate, _is_perfect, _quality_tuple, solve_bracket
from ss_compat import compatible
from ss_quality import colour_terms
from ss_model import Player

_INF = (float("inf"), float("inf"))
SEARCH_NODES = 20_000  # Arbeitsbudget der gezielten Suche je Downfloater-Menge (Phase 2)


def bye_key(player: Player) -> tuple[float, int]:
    """[C5] dann [C9], beide zu minimieren."""
    return player.score, player.unplayed_games


class _Chain:
    def __init__(
        self,
        groups: list[tuple[float, list[int]]],
        players: dict[int, Player],
        threshold: float,
        excluded_from_bye: frozenset[int],
        bye_cap: tuple[float, int],
    ):
        self.groups = groups
        self.players = players
        self.threshold = threshold
        self.excluded_from_bye = excluded_from_bye
        self.bye_cap = bye_cap
        self.ctx = BracketContext(players=players, topscorer_threshold=threshold)
        self._edges: dict[tuple[int, int], bool] = {}
        self._memo: dict[tuple, tuple | None] = {}
        self._terms: dict[tuple[int, int], tuple | None] = {}

    # --- Bausteine ---------------------------------------------------------------------------------

    def edge(self, a: int, b: int) -> bool:
        key = (a, b) if a < b else (b, a)
        hit = self._edges.get(key)
        if hit is None:
            hit = self._edges[key] = compatible(self.players[key[0]], self.players[key[1]], self.threshold)
        return hit

    def own_key(self, downfloaters: tuple[int, ...]) -> tuple:
        """[C6]/[C7] eines Blocks: Zahl und Scores (absteigend) der herausfallenden Spieler; kleiner = besser."""
        return len(downfloaters), tuple(sorted((self.players[r].score for r in downfloaters), reverse=True))

    def bye_allowed(self, rank: int) -> bool:
        player = self.players[rank]
        return not player.had_bye_or_equivalent and rank not in self.excluded_from_bye and bye_key(player) <= self.bye_cap

    def _matching_exists(self, vertices: tuple[int, ...], mdps: frozenset[int]) -> bool:
        """Perfektes Matching der `vertices`: erlaubt sind verträgliche Paare, aber nie zwei MDPs miteinander
        (MDPs werden mit Residenten gepaart, Art. 3.7)."""
        n = len(vertices)
        if n % 2:
            return False
        adjacent = [0] * n
        for i in range(n):
            for j in range(i + 1, n):
                a, b = vertices[i], vertices[j]
                if self.edge(a, b) and not (a in mdps and b in mdps):
                    adjacent[i] |= 1 << j
                    adjacent[j] |= 1 << i
        failed: set[int] = set()

        def match(mask: int) -> bool:
            if not mask:
                return True
            if mask in failed:
                return False
            low = mask & -mask
            v = low.bit_length() - 1
            options = adjacent[v] & mask & ~low
            while options:
                bit = options & -options
                options ^= bit
                if match(mask ^ low ^ bit):
                    return True
            failed.add(mask)
            return False

        return match((1 << n) - 1)

    def _matching_pairs(self, vertices: tuple[int, ...], mdps: frozenset[int]) -> list[tuple[int, int]] | None:
        """Irgendein perfektes Matching (nur als Rückfall, wenn der Kandidatenstrom die gewählte Menge nicht enthält)."""
        n = len(vertices)
        adjacent = [0] * n
        for i in range(n):
            for j in range(i + 1, n):
                a, b = vertices[i], vertices[j]
                if self.edge(a, b) and not (a in mdps and b in mdps):
                    adjacent[i] |= 1 << j
                    adjacent[j] |= 1 << i

        def match(mask: int) -> list[tuple[int, int]] | None:
            if not mask:
                return []
            low = mask & -mask
            v = low.bit_length() - 1
            options = adjacent[v] & mask & ~low
            while options:
                bit = options & -options
                options ^= bit
                rest = match(mask ^ low ^ bit)
                if rest is not None:
                    return [(vertices[v], vertices[bit.bit_length() - 1])] + rest
            return None

        return match((1 << n) - 1)

    # --- Phase 1 -------------------------------------------------------------------------------------

    def best(self, k: int, incoming: tuple[int, ...], may_reduce: bool) -> tuple | None:
        """Bester Rest ab Block `k` bei den hereinfallenden Spielern `incoming`: `(Profil, Mengen)` oder None.
        `Profil` = ([C6]/[C7]-Schlüssel je Block ab k); `Mengen` = die Mengen herausfallender Spieler dieses Blocks,
        die dieses Profil erreichen."""
        key = (k, incoming, may_reduce)
        if key in self._memo:
            return self._memo[key]
        result = self._best(k, incoming, may_reduce)
        self._memo[key] = result
        return result

    def _best(self, k: int, incoming: tuple[int, ...], may_reduce: bool) -> tuple | None:
        if k == len(self.groups):
            if not incoming:
                return (), []
            if len(incoming) == 1 and self.bye_allowed(incoming[0]):
                return (), []
            return None

        residents = self.groups[k][1]
        mdps = frozenset(incoming)
        pool = tuple(sorted(incoming + tuple(residents)))
        n = len(pool)
        # Strukturelles Maximum der Paarzahl ohne Verträglichkeitsprüfung (wie `ss_engine`): MDPs paaren nur
        # mit Residenten. Weniger Paare (mehr Downfloater) nur, wenn dieser Block reduzieren darf.
        structural_downfloaters = n - 2 * min(n // 2, len(residents))
        counts = range(structural_downfloaters, n + 1, 2) if may_reduce else [structural_downfloaters]

        for count in counts:
            options = sorted(((self.own_key(chosen), chosen) for chosen in combinations(pool, count)), key=lambda t: t[0])
            for own_key, group in groupby(options, key=lambda t: t[0]):
                best_profile: tuple | None = None
                winners: list[tuple[int, ...]] = []
                for _, chosen in group:
                    chosen_set = set(chosen)
                    remaining = tuple(r for r in pool if r not in chosen_set)
                    if not self._matching_exists(remaining, mdps):
                        continue
                    rest = self.best(k + 1, chosen, True)
                    if rest is None:
                        continue
                    if best_profile is None or rest[0] < best_profile:
                        best_profile, winners = rest[0], [chosen]
                    elif rest[0] == best_profile:
                        winners.append(chosen)
                if best_profile is not None:
                    return (own_key,) + best_profile, winners
        return None

    # --- Phase 2 -------------------------------------------------------------------------------------

    def solve(self, may_reduce_first: bool) -> tuple[list[tuple[int, int]], int | None] | None:
        if self.best(0, (), may_reduce_first) is None:
            return None
        pairs: list[tuple[int, int]] = []
        incoming: tuple[int, ...] = ()
        for k, (_, residents) in enumerate(self.groups):
            outcome = self.best(k, incoming, may_reduce_first if k == 0 else True)
            wanted = set(outcome[1])
            chosen = None
            for candidate in solve_bracket(residents, list(incoming), self.ctx):
                if tuple(sorted(candidate.downfloaters)) in wanted:
                    chosen = candidate
                    break
            # Der Kandidatenstrom der Bracket-Suche ist gedeckelt und kann die beste Paarung einer Menge
            # auslassen (gemessen: in einem Block mit zwei hereingefloateten Spielern fehlte die farblich
            # perfekte Paarung ganz). Deshalb je gewählter Menge zusätzlich gezielt suchen; nur eine strikt
            # bessere Qualität ersetzt den Kandidaten aus dem Strom.
            chosen = self._improve(residents, incoming, wanted, chosen)
            if chosen is not None:
                pairs.extend(chosen.pairs)
                incoming = tuple(sorted(chosen.downfloaters))
                continue
            # Rückfall: der (gedeckelte) Kandidatenstrom enthält die gewählte Menge nicht - irgendeine gültige
            # Paarung für die erste gewählte Menge nehmen.
            downfloaters = sorted(wanted)[0]
            pool = tuple(sorted(incoming + tuple(residents)))
            remaining = tuple(r for r in pool if r not in set(downfloaters))
            fallback = self._matching_pairs(remaining, frozenset(incoming))
            if fallback is None:
                return None
            pairs.extend(fallback)
            incoming = tuple(downfloaters)
        return pairs, (incoming[0] if incoming else None)


    def _improve(self, residents: list[int], incoming: tuple[int, ...], wanted: set[tuple[int, ...]], chosen: Candidate | None) -> Candidate | None:
        mdps = frozenset(incoming)
        best = chosen
        best_rank = None  # (Qualität, Erzeugungsschlüssel); der Kandidat aus dem Strom gewinnt jeden Gleichstand
        if chosen is not None:
            best_rank = (self._quality(chosen.pairs, chosen.downfloaters, mdps), ())
            if _is_perfect(best_rank[0]):
                # Der Strom liest einen ANFANG der Erzeugungsreihenfolge: ein perfekter Kandidat daraus ist der
                # erste perfekte überhaupt, ein fehlender käme erst danach. Nichts zu verbessern.
                return chosen
        for downfloaters in sorted(wanted):
            found = self._best_for_set(residents, incoming, downfloaters, best_rank[0] if best_rank else None)
            if found is not None and (best_rank is None or (found[1], found[2]) < best_rank):
                best, best_rank = found[0], (found[1], found[2])
        return best

    def _quality(self, pairs, downfloaters, mdps: frozenset[int]) -> tuple:
        residents_out = [r for r in downfloaters if r not in mdps]
        return _quality_tuple(list(pairs), residents_out, mdps, self.players, self.threshold)

    def _colour_terms(self, a: int, b: int) -> tuple[int, int, int, int] | None:
        """(C10-C13) des Paars, oder None, wenn es nicht erlaubt ist (C1/C3)."""
        key = (a, b) if a < b else (b, a)
        if key not in self._terms:
            self._terms[key] = colour_terms(self.players[key[0]], self.players[key[1]], self.threshold) if self.edge(a, b) else None
        return self._terms[key]

    def _best_for_set(self, residents: list[int], incoming: tuple[int, ...], downfloaters: tuple[int, ...],
                      incumbent: tuple | None) -> tuple[Candidate, tuple, tuple[int, ...]] | None:
        """Beste Paarung für genau diese Downfloater-Menge, die `incumbent` nicht überbietet, in der
        Erzeugungsreihenfolge des Regeltexts: erst werden die MDPs (Art. 1.2) der Reihe nach mit aufsteigenden
        Residenten gepaart (Art. 3.7), dann der Rest der Residenten R' als homogene Bracket (Art. 3.3):
        S1 = die ersten p von R', S2 = der Rest, Paare S1[i] gegen eine Anordnung der in S2 verbleibenden
        Spieler (Transposition, Art. 4.2). Gleich gute Kandidaten verschiedener Mengen entscheidet so dieselbe
        Reihenfolge wie die vollständige Aufzählung: der Schlüssel (MDP-Zuordnung, Anordnung) ist lexikografisch
        zu minimieren. Mengen, die nur über Tausch-Aufteilungen (Art. 4.3) erreichbar sind, kommen danach.

        Tiefensuche mit Schranke: die Teilsumme C10-C13 ist eine untere Schranke. Gibt (Kandidat, Qualität,
        Schlüssel) zurück."""
        out = set(downfloaters)
        mdps = frozenset(incoming)
        to_pair = sorted((m for m in incoming if m not in out), key=lambda r: (-self.players[r].score, r))
        all_residents = sorted(residents)
        down_residents = [r for r in downfloaters if r not in mdps]
        usable = [r for r in all_residents if r not in out]
        if (len(to_pair) + len(usable)) % 2:
            return None
        found: list = []  # [(Qualität, Paare, Schlüssel)]
        budget = [SEARCH_NODES]
        sums = [0, 0, 0, 0]
        mdp_pairs: list[tuple[int, int]] = []
        used_by_mdp: set[int] = set()
        limit = incumbent[:4] if incumbent is not None else None

        def bound_exceeded() -> bool:
            bound = found[0][0][:4] if found else limit
            return bound is not None and tuple(sums) > bound

        def record(pairs: list[tuple[int, int]], key: tuple[int, ...]) -> None:
            quality = self._quality(pairs, downfloaters, mdps)
            if not found:
                if incumbent is None or quality <= incumbent:
                    found[:] = [(quality, list(pairs), key)]
            elif quality < found[0][0]:
                found[:] = [(quality, list(pairs), key)]

        def remainder() -> bool:
            rest = [r for r in all_residents if r not in used_by_mdp]
            pairs_needed = (len(rest) - len(down_residents)) // 2
            if (len(rest) - len(down_residents)) % 2 or pairs_needed < 0:
                return False
            first, second = rest[:pairs_needed], rest[pairs_needed:]
            if any(r not in second for r in down_residents):
                return False  # nur über Tausch-Aufteilungen erreichbar
            chosen_from = [r for r in second if r not in down_residents]
            taken = [False] * len(chosen_from)
            partners: list[int] = []
            pairs: list[tuple[int, int]] = []
            mdp_key = tuple(b for _, b in mdp_pairs)

            def assign(depth: int) -> bool:
                if depth == len(first):
                    record(mdp_pairs + pairs, mdp_key + tuple(partners))
                    return False
                for i, candidate in enumerate(chosen_from):
                    if taken[i]:
                        continue
                    budget[0] -= 1
                    if budget[0] <= 0:
                        return True
                    info = self._colour_terms(first[depth], candidate)
                    if info is None:
                        continue
                    for k in range(4):
                        sums[k] += info[k]
                    stop = False
                    if not bound_exceeded():
                        taken[i] = True
                        partners.append(candidate)
                        pairs.append((first[depth], candidate))
                        stop = assign(depth + 1)
                        pairs.pop()
                        partners.pop()
                        taken[i] = False
                    for k in range(4):
                        sums[k] -= info[k]
                    if stop:
                        return True
                return False

            return assign(0)

        def assign_mdps(index: int) -> bool:
            if index == len(to_pair):
                return remainder()
            for resident in usable:
                if resident in used_by_mdp:
                    continue
                budget[0] -= 1
                if budget[0] <= 0:
                    return True
                info = self._colour_terms(to_pair[index], resident)
                if info is None:
                    continue
                for k in range(4):
                    sums[k] += info[k]
                stop = False
                if not bound_exceeded():
                    used_by_mdp.add(resident)
                    mdp_pairs.append((to_pair[index], resident))
                    stop = assign_mdps(index + 1)
                    mdp_pairs.pop()
                    used_by_mdp.discard(resident)
                for k in range(4):
                    sums[k] -= info[k]
                if stop:
                    return True
            return False

        assign_mdps(0)
        if found:
            quality, best_pairs, key = found[0]
            return Candidate(pairs=tuple(best_pairs), downfloaters=tuple(sorted(downfloaters))), quality, (0,) + key
        return self._best_for_set_general(residents, incoming, downfloaters, incumbent)

    def _best_for_set_general(self, residents: list[int], incoming: tuple[int, ...], downfloaters: tuple[int, ...],
                              incumbent: tuple | None) -> tuple[Candidate, tuple, tuple[int, ...]] | None:
        """Rückfall ohne die Erzeugungsstruktur des Regeltexts. Beste Paarung der Spieler außerhalb von `downfloaters` (MDPs nur mit Residenten, Art. 3.7), die
        `incumbent` nicht überbietet (gleich gute zählen, damit bei Gleichstand die Erzeugungsreihenfolge über
        alle Mengen hinweg entscheidet) - Tiefensuche mit Schranke in der Reihenfolge: MDPs nach Art. 1.2, dann
        der kleinste ungepaarte Resident mit aufsteigenden Partnern. Die Schranke ist die Teilsumme C10-C13.
        Gibt (Kandidat, Qualität, Erzeugungsschlüssel) zurück; der Schlüssel ist die Folge der gewählten Partner
        in Suchreihenfolge, lexikografisch aufsteigend wie die Transpositionen des Regeltexts (Art. 4.2)."""
        out = set(downfloaters)
        mdps = frozenset(incoming)
        order = sorted((m for m in incoming if m not in out), key=lambda r: (-self.players[r].score, r))
        order += sorted(r for r in residents if r not in out)
        n = len(order)
        if n % 2:
            return None
        paired = [False] * n
        pairs: list[tuple[int, int]] = []
        sums = [0, 0, 0, 0]
        found: list = []  # [(Qualität, Paare)]
        budget = [SEARCH_NODES]
        limit = incumbent[:4] if incumbent is not None else None

        def descend() -> bool:
            if len(pairs) * 2 == n:
                quality = self._quality(pairs, downfloaters, mdps)
                if not found:
                    if incumbent is None or quality <= incumbent:
                        found[:] = [(quality, list(pairs))]
                elif quality < found[0][0]:
                    found[:] = [(quality, list(pairs))]
                return False
            first = paired.index(False)
            for j in range(first + 1, n):
                if paired[j]:
                    continue
                budget[0] -= 1
                if budget[0] <= 0:
                    return True
                if order[first] in mdps and order[j] in mdps:
                    continue
                info = self._colour_terms(order[first], order[j])
                if info is None:
                    continue
                for k in range(4):
                    sums[k] += info[k]
                bound = found[0][0][:4] if found else limit
                prune = bound is not None and tuple(sums) > bound
                stop = False
                if not prune:
                    paired[first] = paired[j] = True
                    pairs.append((order[first], order[j]))
                    stop = descend()
                    pairs.pop()
                    paired[first] = paired[j] = False
                for k in range(4):
                    sums[k] -= info[k]
                if stop:
                    return True
            return False

        descend()
        if not found:
            return None
        quality, best_pairs = found[0]
        key = (1,) + tuple(b for _, b in best_pairs)  # nach allen Kandidaten ohne Tausch
        return Candidate(pairs=tuple(best_pairs), downfloaters=tuple(sorted(downfloaters))), quality, key


def solve_round(
    groups: list[tuple[float, list[int]]],
    players: dict[int, Player],
    threshold: float,
    excluded_from_bye: frozenset[int] = frozenset(),
) -> tuple[list[tuple[int, int]], int | None] | None:
    """Beste vollständige Runde nach C5-C9 (und C10-C21 darunter), oder None, wenn keine existiert ([C4]).

    Gerade Zahl: kein Freilos, die Obergrenze entfällt. Ungerade Zahl: die Obergrenze für den Freilos-Schlüssel
    (Score, ungespielte Partien) steigt über die Schlüssel der freilosberechtigten Spieler, bis eine Runde
    existiert ([C5] vor allem anderen). Je Obergrenze erst ohne, dann mit Reduktion im ersten Block."""
    total = sum(len(residents) for _, residents in groups)
    if total % 2 == 0:
        caps = [_INF]
    else:
        eligible = sorted({bye_key(p) for r, p in players.items() if not p.had_bye_or_equivalent and r not in excluded_from_bye})
        caps = eligible
    for cap in caps:
        chain = _Chain(groups, players, threshold, excluded_from_bye, cap)
        for may_reduce_first in (False, True):
            result = chain.solve(may_reduce_first)
            if result is not None:
                return result
    return None
