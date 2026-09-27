"""Edmonds' gewichteter Blossom-Algorithmus - schlanker Kern, portiert aus
`weighted-blossom-demo/wb_blossom.py` (Galil 1986, dieselbe primal-duale Methode wie
`networkx.max_weight_matching`).

**Unterschied zu `wb_blossom.py`**: dort ist der Löser das eigentliche Demo-Thema, mit
vollem Ereignisprotokoll (jede Runde, jede Kontraktion, jeder Delta-Schritt als
`Event`/`Snapshot`) für die Schritt-für-Schritt-Visualisierung. Hier ist der Löser nur
ein INTERNES Werkzeug für die Kriterien C9-C21 (die Paarung selbst ist das Thema dieser
Demo, nicht der Matching-Algorithmus) - deshalb ohne Protokollierung, nur das Ergebnis
(`pairs`). Die Dualwert-Arithmetik (assignLabel/scanBlossom/addBlossom/expandBlossom/
augmentBlossom/augmentMatching, Delta-Typen 1-4) ist UNVERÄNDERT aus `wb_blossom.py`
übernommen - siehe dort für die ausführliche Herleitung/Fallstrick-Dokumentation.

**Kardinalität.** `max_weight_perfect_matching` braucht immer eine PERFEKTE Paarung (alle Knoten
gepaart) - die ganze Runde wird als EIN Matching über alle aktiven Spieler PLUS einen virtuellen
Freilos-Knoten gelöst (`ss_engine.py`), keine separate Downfloater-Vorauswahl mehr nötig: Bracket-
Priorität (C6-C9) steckt direkt in den Kantengewichten (`ss_weights.py`), nicht in einer
sequenziellen Bracket-für-Bracket-Verarbeitung - siehe `project_turnierplanung_dag_scoping.md` für
die Architekturbegründung. Intern derselbe `(maxcost+1)`-Trick wie in `wb_blossom.py`
(`maxcardinality=True`): macht jede Kante lohnend, sodass die interne Maximierung nie freiwillig
einen Knoten unpaarig lässt, wenn eine perfekte Paarung möglich ist.
"""

from __future__ import annotations


class _Blossom:
    __slots__ = ["childs", "edges", "mybestedges"]

    def leaves(self):
        stack = [*self.childs]
        while stack:
            t = stack.pop()
            if isinstance(t, _Blossom):
                stack.extend(t.childs)
            else:
                yield t


class _NoNode:
    pass


class NoValidPairingError(ValueError):
    """Für diese Runde existiert keine Paarung, die alle absoluten Kriterien (C1-C3) gleichzeitig
    erfüllt - ein echter, in der FIDE-Praxis vorkommender Fall (bbpPairings meldet denselben
    Zustand als eigenen Fehlercode 1: "No valid pairing exists"), keine Ausnahme/kein Bug."""


def max_weight_perfect_matching(n: int, adj: list[list[int]], weight: dict[tuple[int, int], int]) -> dict[int, int]:
    """n Knoten (0..n-1), adj[v] = Nachbarliste, weight[(min(i,j),max(i,j))] = nicht-negatives
    Gewicht. Wirft `NoValidPairingError`, wenn keine perfekte Paarung existiert (z. B. weil unter
    den verbliebenen Spielern jedes Paar schon einmal gegeneinander gespielt hat - siehe
    `NoValidPairingError`)."""
    if n % 2 != 0:
        raise ValueError("max_weight_perfect_matching braucht eine gerade Knotenzahl")
    mate = _solve(n, adj, weight)
    if len(mate) != n:
        raise NoValidPairingError("keine Paarung erfüllt für alle Spieler gleichzeitig C1-C3")
    return mate


def maximum_cardinality_matching(n: int, adj: list[list[int]]) -> dict[int, int]:
    """Größtmögliche (nicht notwendig perfekte) Paarung - nur für `ss_downfloat.py`s
    Vervollständigbarkeits-Probe (C8): zählt, wie viele Spieler sich überhaupt paaren lassen,
    unabhängig von C9-C21 (dafür genügt ein einheitliches Gewicht 1 auf jeder zulässigen Kante -
    der `(maxcost+1)`-Mechanismus maximiert dann automatisch zuerst die Anzahl)."""
    return _solve(n, adj, {})


def _solve(n: int, adj: list[list[int]], weight: dict[tuple[int, int], int]) -> dict[int, int]:
    if n == 0:
        return {}

    feasible = [(i, j) for i in range(n) for j in adj[i] if i < j]
    if not feasible:
        return {}

    def iw(i, j):
        # Anders als wb_blossom.py (das intern MINIMIERT und darum cost -> (maxcost+1)-cost dreht):
        # hier wird direkt MAXIMIERT (größeres C9-C21-Gewicht = besser), also OHNE Vorzeichen-/
        # Verschiebungstrick - das Gewicht selbst ist bereits die zu maximierende Größe. Die
        # Perfektheits-Priorität (maxcardinality) kommt allein aus `dualvar[v] = maxiw` für alle v
        # (macht anfangs nur die größten Kanten straff, die Suche wächst von dort über alle
        # Knoten), exakt wie networkx' eigenes max_weight_matching(..., maxcardinality=True).
        # Leeres `weight`-Dict (maximum_cardinality_matching) -> einheitliches Gewicht 1 auf jeder
        # zulässigen Kante, damit ausschließlich die Kardinalität zählt.
        return weight.get((i, j) if i < j else (j, i), 1) if weight else 1

    maxiw = max([0] + [iw(i, j) for i, j in feasible])

    NONODE = _NoNode()
    mate: dict = {}
    label: dict = {}
    labeledge: dict = {}
    inblossom = {v: v for v in range(n)}
    blossomparent = {v: None for v in range(n)}
    blossombase = {v: v for v in range(n)}
    bestedge: dict = {}
    dualvar = {v: maxiw for v in range(n)}
    blossomdual: dict = {}
    allowedge: dict = {}
    queue: list = []

    def slack(v, w):
        return dualvar[v] + dualvar[w] - 2 * iw(v, w)

    def assignLabel(w, t, v):
        b = inblossom[w]
        label[w] = label[b] = t
        labeledge[w] = labeledge[b] = (v, w) if v is not None else None
        bestedge[w] = bestedge[b] = None
        if t == 1:
            if isinstance(b, _Blossom):
                queue.extend(b.leaves())
            else:
                queue.append(b)
        elif t == 2:
            base = blossombase[b]
            assignLabel(mate[base], 1, base)

    def scanBlossom(v, w):
        path = []
        base = NONODE
        while v is not NONODE:
            b = inblossom[v]
            if label[b] & 4:
                base = blossombase[b]
                break
            path.append(b)
            label[b] = 5
            if labeledge.get(b) is None:
                v = NONODE
            else:
                v = labeledge[b][0]
                b = inblossom[v]
                v = labeledge[b][0]
            if w is not NONODE:
                v, w = w, v
        for b in path:
            label[b] = 1
        return base

    def addBlossom(base, v, w):
        bb = inblossom[base]
        bv = inblossom[v]
        bw = inblossom[w]
        b = _Blossom()
        blossombase[b] = base
        blossomparent[b] = None
        blossomparent[bb] = b
        b.childs = path = []
        b.edges = edgs = [(v, w)]
        while bv != bb:
            blossomparent[bv] = b
            path.append(bv)
            edgs.append(labeledge[bv])
            v = labeledge[bv][0]
            bv = inblossom[v]
        path.append(bb)
        path.reverse()
        edgs.reverse()
        while bw != bb:
            blossomparent[bw] = b
            path.append(bw)
            edgs.append((labeledge[bw][1], labeledge[bw][0]))
            w = labeledge[bw][0]
            bw = inblossom[w]
        label[b] = 1
        labeledge[b] = labeledge[bb]
        blossomdual[b] = 0

        for leaf in b.leaves():
            if label.get(inblossom[leaf]) == 2:
                queue.append(leaf)
            inblossom[leaf] = b
        bestedgeto = {}
        for bv2 in path:
            if isinstance(bv2, _Blossom):
                if bv2.mybestedges is not None:
                    nblist = bv2.mybestedges
                    bv2.mybestedges = None
                else:
                    nblist = [(lv, wv) for lv in bv2.leaves() for wv in adj[lv] if lv != wv]
            else:
                nblist = [(bv2, wv) for wv in adj[bv2] if bv2 != wv]
            for (i2, j2) in nblist:
                if inblossom[j2] == b:
                    i2, j2 = j2, i2
                bj = inblossom[j2]
                if bj != b and label.get(bj) == 1 and ((bj not in bestedgeto) or slack(i2, j2) < slack(*bestedgeto[bj])):
                    bestedgeto[bj] = (i2, j2)
            bestedge[bv2] = None
        b.mybestedges = list(bestedgeto.values())
        mybestedge, mybestslack = None, None
        bestedge[b] = None
        for k in b.mybestedges:
            kslack = slack(*k)
            if mybestedge is None or kslack < mybestslack:
                mybestedge, mybestslack = k, kslack
        bestedge[b] = mybestedge
        return b

    def expandBlossom(b, endstage):
        for s in b.childs:
            blossomparent[s] = None
            if isinstance(s, _Blossom):
                if endstage and blossomdual[s] == 0:
                    expandBlossom(s, True)
                    continue
                for leaf in s.leaves():
                    inblossom[leaf] = s
            else:
                inblossom[s] = s
        if (not endstage) and label.get(b) == 2:
            entrychild = inblossom[labeledge[b][1]]
            j = b.childs.index(entrychild)
            if j & 1:
                j -= len(b.childs)
                jstep = 1
            else:
                jstep = -1
            v, w = labeledge[b]
            while j != 0:
                if jstep == 1:
                    p, q = b.edges[j]
                else:
                    q, p = b.edges[j - 1]
                label[w] = None
                label[q] = None
                assignLabel(w, 2, v)
                allowedge[(p, q)] = allowedge[(q, p)] = True
                j += jstep
                if jstep == 1:
                    v, w = b.edges[j]
                else:
                    w, v = b.edges[j - 1]
                allowedge[(v, w)] = allowedge[(w, v)] = True
                j += jstep
            bw = b.childs[j]
            label[w] = label[bw] = 2
            labeledge[w] = labeledge[bw] = (v, w)
            bestedge[bw] = None
            j += jstep
            while b.childs[j] != entrychild:
                bv = b.childs[j]
                if label.get(bv) == 1:
                    j += jstep
                    continue
                if isinstance(bv, _Blossom):
                    vv = None
                    for leaf in bv.leaves():
                        if label.get(leaf):
                            vv = leaf
                            break
                else:
                    vv = bv
                if vv is not None and label.get(vv):
                    label[vv] = None
                    label[mate[blossombase[bv]]] = None
                    assignLabel(vv, 2, labeledge[vv][0])
                j += jstep
        label.pop(b, None)
        labeledge.pop(b, None)
        bestedge.pop(b, None)
        del blossomparent[b]
        del blossombase[b]
        del blossomdual[b]

    def augmentBlossom(b, v):
        t = v
        while blossomparent[t] != b:
            t = blossomparent[t]
        if isinstance(t, _Blossom):
            augmentBlossom(t, v)
        i = j = b.childs.index(t)
        if i & 1:
            j -= len(b.childs)
            jstep = 1
        else:
            jstep = -1
        while j != 0:
            j += jstep
            t = b.childs[j]
            if jstep == 1:
                w, x = b.edges[j]
            else:
                x, w = b.edges[j - 1]
            if isinstance(t, _Blossom):
                augmentBlossom(t, w)
            j += jstep
            t = b.childs[j]
            if isinstance(t, _Blossom):
                augmentBlossom(t, x)
            mate[w] = x
            mate[x] = w
        b.childs = b.childs[i:] + b.childs[:i]
        b.edges = b.edges[i:] + b.edges[:i]
        blossombase[b] = blossombase[b.childs[0]]

    def augmentMatching(v, w):
        for s, j in ((v, w), (w, v)):
            while True:
                bs = inblossom[s]
                if isinstance(bs, _Blossom):
                    augmentBlossom(bs, s)
                mate[s] = j
                if labeledge.get(bs) is None:
                    break
                t = labeledge[bs][0]
                bt = inblossom[t]
                s, j = labeledge[bt]
                if isinstance(bt, _Blossom):
                    augmentBlossom(bt, j)
                mate[j] = s

    while True:
        label.clear()
        labeledge.clear()
        bestedge.clear()
        for b in blossomdual:
            b.mybestedges = None
        allowedge.clear()
        queue[:] = []
        for v in range(n):
            if v not in mate and label.get(inblossom[v]) is None:
                assignLabel(v, 1, None)

        augmented = False
        while True:
            while queue and not augmented:
                v = queue.pop()
                for w in adj[v]:
                    bv, bw = inblossom[v], inblossom[w]
                    if bv == bw:
                        continue
                    if (v, w) not in allowedge:
                        if slack(v, w) <= 0:
                            allowedge[(v, w)] = allowedge[(w, v)] = True
                    if (v, w) in allowedge:
                        if label.get(bw) is None:
                            assignLabel(w, 2, v)
                        elif label.get(bw) == 1:
                            base = scanBlossom(v, w)
                            if base is not NONODE:
                                addBlossom(base, v, w)
                            else:
                                augmentMatching(v, w)
                                augmented = True
                                break
                        elif label.get(w) is None:
                            label[w] = 2
                            labeledge[w] = (v, w)
                    elif label.get(bw) == 1:
                        if bestedge.get(bv) is None or slack(v, w) < slack(*bestedge[bv]):
                            bestedge[bv] = (v, w)
                    elif label.get(w) is None:
                        if bestedge.get(w) is None or slack(v, w) < slack(*bestedge[w]):
                            bestedge[w] = (v, w)
                if augmented:
                    break

            if augmented:
                break

            deltatype, delta, deltaedge, deltablossom = -1, None, None, None
            for v in range(n):
                if label.get(inblossom[v]) is None and bestedge.get(v) is not None:
                    d = slack(*bestedge[v])
                    if deltatype == -1 or d < delta:
                        delta, deltatype, deltaedge = d, 2, bestedge[v]
            for b in list(blossomparent):
                if blossomparent[b] is None and label.get(b) == 1 and bestedge.get(b) is not None:
                    d = slack(*bestedge[b]) // 2
                    if deltatype == -1 or d < delta:
                        delta, deltatype, deltaedge = d, 3, bestedge[b]
            for b in blossomdual:
                if blossomparent[b] is None and label.get(b) == 2 and (deltatype == -1 or blossomdual[b] < delta):
                    delta, deltatype, deltablossom = blossomdual[b], 4, b
            if deltatype == -1:
                deltatype, delta = 1, max(0, min(dualvar.values()))

            for v in range(n):
                lb = label.get(inblossom[v])
                if lb == 1:
                    dualvar[v] -= delta
                elif lb == 2:
                    dualvar[v] += delta
            for b in blossomdual:
                if blossomparent[b] is None:
                    lb = label.get(b)
                    if lb == 1:
                        blossomdual[b] += delta
                    elif lb == 2:
                        blossomdual[b] -= delta

            if deltatype == 1:
                break
            elif deltatype in (2, 3):
                (dv, dw) = deltaedge
                allowedge[(dv, dw)] = allowedge[(dw, dv)] = True
                queue.append(dv)
            elif deltatype == 4:
                expandBlossom(deltablossom, False)

        if not augmented:
            break
        for b in list(blossomdual.keys()):
            if b not in blossomdual:
                continue
            if blossomparent.get(b) is None and label.get(b) == 1 and blossomdual[b] == 0:
                expandBlossom(b, True)

    return dict(mate)
