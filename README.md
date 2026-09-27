# Schweizer System (FIDE Dutch System) – Streamlit-Demo

**[→ Demo live ausprobieren](https://sebastianhanisch-schweizer-system-demo.streamlit.app/)**

Drittes und letztes Stück der **Turnierplanung-Linie** der "Konzepte"-Reihe für die Website "Sebastian Hanisch –
Operations Research und Machine Learning". Ein Rundenturnier (Stück 1) braucht n−1 Runden, ein K.-o.-System
(Stück 2) opfert dafür fast alle Spieler nach einer Niederlage. Das **Schweizer System** löst beides: eine feste,
kleine Rundenzahl, bei der (fast) alle Teilnehmer viele Partien spielen. Diese Demo baut den Paarungsalgorithmus
**nach dem echten FIDE-Regelwerk** (C.04.3, "Dutch System") nach – alle 21 Kriterien, Farbzuteilung, Freilos-
Regeln – und prüft ihn direkt gegen [bbpPairings](https://github.com/BieremaBoyzProgramming/bbpPairings), die
offizielle, FIDE-anerkannte Referenz-Engine.

```
Rundenturnier (Stück 1, gebaut+gepusht+deployed)
 ├─ K.-o.-System + Setzliste (Stück 2, gebaut+gepusht+deployed)
 └─ Schweizer System (dieses Stück, komplexestes der Linie)
```

## Ergebnis (Zahlen aus den Tests)

| Frage | Ergebnis |
|---|---|
| Gelten die absoluten Kriterien (C1-C3) immer? | ✅ **Beweisbar ja** – eine verbotene Paarung existiert als Kante im Matching-Graphen schlicht nicht, kein separater Check nötig. |
| Wird Runde 1 (frisches Feld) korrekt nachgebildet? | ✅ **100 %** – die "obere Hälfte gegen untere Hälfte"-Standardaufteilung stimmt exakt mit bbpPairings überein (verifiziert für 4–10 Spieler). |
| Stimmen die zwei mitgelieferten bbpPairings-Testfixturen exakt? | ✅ `dutch_2025_C5` und `dutch_2025_C9` (echte FIDE-Testfälle) werden Zahl für Zahl reproduziert. |
| Wie genau sind die Qualitätskriterien (C6-C21) insgesamt? | ⚠️ **~66 %** exakte Übereinstimmung mit bbpPairings auf zufälligen Mehrrundenturnieren (4–10 Spieler, 1–3 Runden, gemessen über 300+ Vergleiche). Der Rest liegt an bbpPairings' eigener, nicht dokumentierter interner Gewichtsstaffelung für Tie-Breaks – mehrere konkrete Hypothesen wurden getestet und wieder verworfen. |
| Bleibt der Farbausgleich fair? | ✅ Weiß/Schwarz-Differenz bleibt in jedem gemessenen Turnier bei höchstens 1 je Spieler. |

## Architektur (eine bewusste Kehrtwende während des Baus)

Die erste Implementierung verarbeitete Score-Brackets **sequenziell** (eine nach der anderen, mit einer
rekursiven Vervollständigbarkeits-Probe für Downfloater) – das erfüllte alle absoluten Kriterien korrekt, traf
aber bei den Qualitätskriterien nur in ~61 % der zufälligen Testrunden dieselbe Entscheidung wie bbpPairings.
Der Grund, direkt aus bbpPairings' eigenem Quellcode gelesen: die Referenz-Engine löst die **ganze Runde als
EIN gewichtetes Matching**, nicht Bracket für Bracket. Die Engine wurde daraufhin komplett umgebaut – siehe
`project_turnierplanung_dag_scoping.md` für die vollständige Herleitung. Das ist zugleich eine Vereinfachung:
die rekursive Downfloater-Probe entfällt komplett, weil ein perfektes Matching über den Kompatibilitätsgraphen
entweder existiert oder nicht – kein separater Blick nach vorn nötig.

- **`ss_blossom.py`**: schlanker, portierter Kern aus [`weighted-blossom-demo/wb_blossom.py`](https://github.com/sebastian-hanisch/weighted-blossom-demo)
  (Edmonds' gewichteter Blossom-Algorithmus, Galil 1986) – gegen `networkx.max_weight_matching` auf 80+
  Zufallsgraphen verifiziert.
- **`ss_weights.py`**: kodiert alle Kriterien C5-C21 als EINE große Python-`int` je Kante (gemischt-radix,
  höchste Priorität = signifikanteste Stelle) – Python-`int` ist beliebig groß, kein Überlauf wie in bbpPairings'
  eigener C++-Bit-Verschiebung.
- **`ss_engine.py`**: baut den Graphen über alle aktiven Spieler plus einen virtuellen Freilos-Knoten, löst ihn
  mit `ss_blossom`, teilt danach die Farbe zu (`ss_colour.py`, Art. 5.2, ein eigener deterministischer Schritt).

## Was diese Demo (ehrlich) zeigt und was nicht

Die absoluten Kriterien (C1-C3) sind **konstruktiv garantiert**, nicht nur getestet. Die Qualitätskriterien
(C6-C21) sind eine **gute, aber nicht perfekte** Näherung – die gemessene ~66-%-Quote steht so in App und
Tests, nicht schöngerechnet. Konkret identifizierte, aber nicht gelöste Lücken: die exakte Priorisierung
zwischen "wer floatet bei einem Bracket-Größenunterschied" und Farbqualität in bestimmten Randfällen (z. B.
5-Spieler-Felder nach Runde 1) weicht von bbpPairings ab; eine Hypothese ("kleinste Rangdistanz bei erzwungenem
Downfloat") wurde getestet und explizit **verworfen**, weil sie andere Fälle verschlechterte.

## Modell und Verfahren

- **Absolute Kriterien** (Art. 2.1): C1 keine Wiederholung, C2 kein zweites Freilos, C3 keine Kollision
  gleicher absoluter Farbpräferenz (mit Spitzenreiter-Ausnahme).
- **Qualitätskriterien** (Art. 2.4, C5-C21 in dieser Reihenfolge): Freilos-Score, Downfloater-Minimierung,
  Downfloater-Score, Farbqualität, wiederholte Float-Situationen.
- **Farbpräferenz** (Art. 1.7): ABSOLUT (Differenz >1 oder gleiche Farbe zweimal in Folge), STARK (Differenz
  genau ±1), MILD (Differenz 0, alterniert), KEINE.
- **Farbzuteilung** (Art. 5.2): gemeinsame Präferenz zuerst, dann stärkere Einzelpräferenz, dann Alternierung,
  zuletzt Ranglistenposition.
- **Quellen**: [handbook.fide.com/chapter/C0403202602](https://handbook.fide.com/chapter/C0403202602) (FIDE-
  Regeltext), [github.com/BieremaBoyzProgramming/bbpPairings](https://github.com/BieremaBoyzProgramming/bbpPairings)
  (Referenz-Engine, Quellcode und Testfixturen).

## Verifikation

- **Blossom-Kern**: 80+ Zufallsgraphen gegen `networkx.max_weight_matching`, plus Handrechnungen.
- **Exakte Fixturen**: `dutch_2025_C5`, `dutch_2025_C9` (echte bbpPairings-Testfälle) Zahl für Zahl reproduziert.
- **Eigenschaftstests** über viele Zufallsturniere: C1 nie verletzt (gegen volle Historie), C2 nie zweimal
  Freilos, Rundenkardinalität immer korrekt, Determinismus.
- **Oracle-Cross-Check** (`tests/test_oracle_bbppairings.py`, überspringt sich selbst ohne `BBPPAIRINGS_EXE`):
  Runde 1 für mehrere Feldgrößen exakt, gemessene Gesamt-Übereinstimmungsrate mit Sicherheitsmarge geprüft.
- **Streamlit-Rauchtests** (`tests/test_app.py`).

## Dateistruktur

| Datei | Zweck |
|---|---|
| `app.py` | Streamlit-Oberfläche |
| `ss_constants.py` | Regler-Grenzen, Presets |
| `ss_presets.py` | Permalink- und Preset-Logik |
| `ss_model.py` | Datenmodell (Spieler, Partien, Paarungen) |
| `ss_colour.py` | Farbpräferenz-Klassifikation + Zuteilung (Art. 5.2) |
| `ss_compat.py` | C1/C3-Kompatibilitätsprüfung |
| `ss_weights.py` | Kriterien-C5-C21-Kodierung je Kante |
| `ss_blossom.py` | Gewichteter Blossom-Matching-Kern |
| `ss_engine.py` | Orchestrierung: Runde als ein globales Matching lösen |
| `ss_scenario.py` | Turnierfeld + Elo-basierte Simulation |
| `ss_evaluation.py` | Turniertabelle, Kennzahlen |
| `ss_visualization.py` | Plotly: Rundenplan, Turniertabelle, Farbausgleich |
| `ss_oracle_bbppairings.py` | **Nur Tests**: TRF-Schreiber + bbpPairings-Aufruf |
| `tests/` | Blossom-Cross-Check, Fixturen, Eigenschaftstests, Oracle-Vergleich, Rauchtests |

## Lokal starten

```bash
python -m venv venv
venv\Scripts\pip install -r requirements.txt
venv\Scripts\streamlit run app.py
```

## Tests ausführen

```bash
venv\Scripts\pip install -r requirements-dev.txt
venv\Scripts\python -m pytest tests -v
```

Für den Oracle-Cross-Check zusätzlich `BBPPAIRINGS_EXE` auf eine lokale
[bbpPairings](https://github.com/BieremaBoyzProgramming/bbpPairings/releases)-Programmdatei setzen – ohne diese
Variable werden die Oracle-Tests übersprungen, der Rest der Suite läuft trotzdem.

Die CI (`.github/workflows/tests.yml`) läuft auf Ubuntu mit Python 3.12, lädt dafür automatisch die Linux-
Programmdatei von bbpPairings, bei jedem Push und wöchentlich mit den jeweils neuesten Bibliotheksversionen.

---

Diese Demo ist Teil des Portfolios von [Sebastian Hanisch](https://sebastianhanisch.net) – Operations Research
und Machine Learning. Interesse an einer maßgeschneiderten Lösung für Ihr Unternehmen?
[Kontakt aufnehmen](https://sebastianhanisch.net/kontakt.html)
