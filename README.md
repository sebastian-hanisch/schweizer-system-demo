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
| Gelten die absoluten Kriterien (C1-C3) immer? | ✅ **Beweisbar ja** – eine verbotene Paarung wird nie als Kandidat gebildet (`ss_compat.py`), kein separater Check nötig. |
| Wird Runde 1 (frisches Feld) korrekt nachgebildet? | ✅ **100 %** – die "obere Hälfte gegen untere Hälfte"-Standardaufteilung (Art. 3.3.1, wörtlich aus dem Regeltext) stimmt exakt mit bbpPairings überein (verifiziert für 4–10 Spieler). |
| Stimmen die zwei mitgelieferten bbpPairings-Testfixturen exakt? | ✅ `dutch_2025_C5` und `dutch_2025_C9` (echte FIDE-Testfälle) werden Zahl für Zahl reproduziert. |
| Wie genau sind die Qualitätskriterien (C6-C21) insgesamt? | ✅ **~98 %** exakte Übereinstimmung mit bbpPairings auf zufälligen Mehrrundenturnieren (4–16 Spieler, 1–4 Runden, 1427 Vergleiche); auf einer bewusst härteren Stichprobe (6–19 Spieler, bis 6 Runden, mehr Nähe an [C1]-Erschöpfung) **~92 %**. Die restliche Lücke ist ein bekanntes, aus bbpPairings' eigenem Quellcode verstandenes Phänomen (echte Gleichstände, die ein iteratives Neu-Lösen bräuchten) - keine unerklärte Restlücke. |
| Bleibt der Farbausgleich fair? | ✅ Weiß/Schwarz-Differenz bleibt in jedem gemessenen Turnier bei höchstens 1 je Spieler. |

## Architektur (drei bewusste Kehrtwenden während des Baus)

**Erste Fassung**: Score-Brackets **sequenziell** verarbeitet, mit einer rekursiven, aber nur auf Existenz
prüfenden Vervollständigbarkeits-Probe für Downfloater – erfüllte alle absoluten Kriterien korrekt, traf aber
bei den Qualitätskriterien nur in ~61 % der zufälligen Testrunden dieselbe Entscheidung wie bbpPairings.

**Zweite Fassung**: direkt aus bbpPairings' eigenem C++-Quellcode gelesen, dass die Referenz-Engine jede Runde
als EIN gewichtetes allgemeines Matching löst (Galil-Micali-Gabow) statt Bracket für Bracket – die Engine wurde
daraufhin auf genau dieses Modell umgebaut. Das verbesserte die Übereinstimmung auf ~66 %, blieb aber eine
Nachbildung von bbpPairings' eigener Implementierungsstrategie, nicht des FIDE-Regeltexts selbst.

**Dritte, jetzige Fassung**: der FIDE-Regeltext (Art. 3 "Pairing Process for a Bracket" + Art. 4 "Rules for the
Sequential Generation of the Pairings") schreibt tatsächlich ein anderes, eigenes Verfahren vor – kein globales
Matching, sondern eine **Bracket-für-Bracket-Suche mit Transposition und Tausch**: pro Bracket wird zuerst die
"natürliche" Paarung gebildet (Art. 3.3.1: erster Spieler von S1 gegen ersten von S2 usw.), bei Nichterfüllung
aller Kriterien werden Umordnungen (Transposition, Art. 4.2) und danach Tausche zwischen den beiden Gruppen
(Exchange, Art. 4.3) durchprobiert. Diese wörtliche Nachbildung hob die Übereinstimmung zunächst nur auf ~85 %
- eine erste Fassung schätzte per einzelnem Kardinalitäts-Matching, ob eine Bracket-Entscheidung die REST-Runde
noch lösbar hielte, statt es tatsächlich nachzuprüfen. Eine zweite Überarbeitung ersetzte diese Schätzung durch
**echtes Backtracking**: `ss_bracket.py`s Suche liefert nicht mehr nur EINEN geschätzt-besten Kandidaten pro
Bracket, sondern (verzögert/lazy) alle brauchbaren in Prioritätsreihenfolge (Art. 3.8.1); `ss_engine.py`
probiert für jeden ECHT per Rekursion, ob sich die restliche Runde damit zu Ende lösen lässt, und geht erst bei
Fehlschlag zum nächsten Kandidaten über. Dabei wurden fünf weitere, konkrete Fehler gefunden und behoben
(gegen die echte `bbpPairings.exe` verifiziert, nicht nur vermutet):
1. **Farbzuteilung (Art. 5.2.4) fehlte**: wenn beide Spieler dieselbe, durch 5.2.1-5.2.3 nicht auflösbare
   Präferenz hatten, sprang der Code direkt zur reinen Paritätsregel (5.2.5) statt die gemeinsame Präferenz dem
   höherrangigen Spieler zu geben (5.2.4) - ein eigenständiger Bug, unabhängig von der Paarungslogik.
2. **MDP-Paarungen wurden nicht über alle Wahlmöglichkeiten hinweg nach Qualität verglichen**: eine früh
   erzeugte, aber farblich schlechtere MDP-Paarung konnte eine später erzeugte, bessere verdecken, weil nur
   INNERHALB einer festen MDP-Wahl sortiert wurde.
3. **Der Vorrang "weniger Downfloater" (C6) fehlte beim Zusammenführen** verschiedener MDP-Wahlen - eine
   Kandidatenliste wurde rein nach Farb-/Float-Qualität sortiert, ohne dass mehr erreichte Paare zählten.
4. **Eine einzelne MDP-Paarungswahl konnte das ganze Alternativen-Budget aufbrauchen**, bevor andere Wahlen
   überhaupt versucht wurden (behoben mit einem Deckel je Wahl).
5. **Die Anzahl paarbarer MDPs (M1, Art. 3.1.3) wurde rein strukturell bestimmt**, ohne zu prüfen, ob die
   gewählten MDPs überhaupt mit irgendeinem Residenten kompatibel sind (z. B. weil bereits gegen alle gespielt)
   - und wenn nicht, gab es keinen Rückfall auf eine kleinere, tatsächlich erreichbare Zahl.

Das hob die Übereinstimmung von ~85 % auf ~96 % - UND beschleunigte die Suche gleichzeitig drastisch
(32 Spieler/9 Runden: von 11-19 s auf **~0,3 s**), weil die Suche nicht mehr blind bis zu einem festen Budget
durchläuft, sondern beim ersten funktionierenden Kandidaten stoppt. Genau diese neu gewonnene Geschwindigkeit
machte es dann möglich, die verbliebene Lücke noch einmal gezielt zu untersuchen (statt sie als Grenze
hinzunehmen) - dabei kamen vier weitere, unabhängig von bbpPairings.exe verifizierte Bugs zutage:
6. **[C5]/[C9] (Freilos-Score/ungespielte Partien minimieren) wurden gar nicht geprüft**: die Suche akzeptierte
   schlicht die ERSTE vollständige Rundenlösung, auch wenn eine andere (mit niedriger bewertetem
   Freilos-Empfänger) ebenso gültig gewesen wäre. Gefixt mit gezielten, eng begrenzten Nachbesserungs-
   Suchläufen (`_improve_bye_assignment`), die den bisher gefundenen Freilos-Empfänger für einen erneuten
   Versuch künstlich als "schon gehabt" markieren, bis der beweisbar niedrigste Score erreicht ist.
7. **MDPs wurden nicht nach Art. 1.2 (Score absteigend, dann Rang) sortiert weitergereicht** - Downfloater
   wurden nur nach Rang sortiert an die nächste Bracket übergeben, wodurch Art. 4.4s Limbo-Regel ("der
   niedrigst bewertete MDP geht in die Limbo") bei unterschiedlich bewerteten MDPs GENAU VERKEHRT HERUM griff.
8. **Die [C3]-Spitzenreiter-Ausnahme verlangte fälschlich, dass BEIDE Spieler Spitzenreiter sind** - Art. 2.1.3
   sagt "Non-topscorers... shall not meet": die Einschränkung gilt nur für ein Paar aus zwei
   NICHT-Spitzenreitern, ist mindestens einer der beiden Spitzenreiter, greift C3 gar nicht erst.
9. **"Spitzenreiter" (Art. 1.8) wurde falsch definiert**: als Gleichstand mit dem aktuell höchsten Score im
   Feld statt als "Score über 50 % der maximal MÖGLICHEN Punktzahl" (setzt die geplante Gesamtrundenzahl
   voraus, die jetzt als `total_rounds`-Parameter durchgereicht wird). Ein Spieler mit dem aktuell höchsten
   Score ist damit oft noch KEIN Spitzenreiter im Sinne des Regeltexts.

Das hob die Übereinstimmung weiter auf **~98 %** - mit einer damals bewusst offen benannten Grenze: [C8]
(Art. 2.4.3, "die nächste Bracket erreicht ihr eigenes Maximum") wurde nur EINE Bracket weit per Kardinalitäts-
Matching geschätzt, nicht beliebig tief nachgeprüft - eine Entscheidung, die sich erst zwei oder mehr Brackets
weiter unten auswirkt, konnte damit lokal richtig, global aber suboptimal aussehen.

**Vierte Überarbeitung**: diese Grenze wurde geschlossen, indem die 1-Schritt-Schätzung durch **echte,
beliebig tiefe Rekursion** ersetzt wurde - `_solve_round` prüft für einen Kandidaten nicht mehr nur die
UNMITTELBAR nächste Bracket, sondern ruft sich selbst (mit `allow_reduction=False`) auf die komplette
RESTLICHE Kette auf; das ist exakt dieselbe Maschinerie, die schon vorher für den äußersten Rundenversuch
existierte, jetzt konsequent auf jeder Ebene angewendet. Das machte drei weitere, konkrete Probleme sichtbar
und behebbar (kein einziges davon war vorher überhaupt beobachtbar, weil die 1-Schritt-Schätzung sie
verdeckte):
10. **Fehlende Memoisierung ließ die neue tiefe Rekursion pathologisch langsam werden**: dieselbe
    "restliche Bracket-Kette + MDP-Menge" taucht über verschiedene Kandidaten hinweg oft mehrfach auf -
    ohne Zwischenspeicher explodierte das kombinatorisch (gemessen: einzelne 31-32-Spieler-Saatwerte
    brauchten bis zu 44 s). Gefixt mit einem über die ganze Rundenlösung geteilten Cache (Schlüssel:
    Score-Folge + sortierte MDP-Menge + `allow_reduction`) - dabei bewusst NUR echte Erschöpfung cachen,
    nie einen durch Budget-Abbruch erzwungenen Fehlschlag (sonst hätte ein späterer, frisch budgetierter
    Versuch fälschlich denselben "unlösbar"-Cache-Treffer geerbt).
11. **`_improve_bye_assignment` wiederholte denselben erfolglosen Suchlauf bis zu sechsmal**: die Funktion
    schloss nur den bisher BESTEN Freilos-Empfänger von künftigen Versuchen aus - blieb der beste Kandidat
    über eine erfolglose Nachbesserung hinweg unverändert, blieb auch die Ausschlussmenge unverändert, und
    jeder weitere Versuch wiederholte deterministisch exakt denselben, bereits erfolglosen Suchlauf. Gefixt,
    indem JEDER tatsächlich ausprobierte Empfänger ausgeschlossen wird, nicht nur der aktuell beste - jeder
    Versuch liefert jetzt eine echte neue Alternative. Gemessener Fund an genau dem oben erwähnten
    44-s-Fall: nach der Memoisierung lag er bei ~20 s, ausschließlich durch sechs identische Nachbesserungs-
    Wiederholungen - nach diesem zweiten Fix bei 0,15 s.
12. Eine erneute Übereinstimmungsmessung (identische Parameter wie oben: 4-16 Spieler, 1-4 Runden) ergab
    **97,8 %** (701/717) - innerhalb der üblichen Stichprobenschwankung der vorherigen ~98 %-Messung, also
    **keine Regression**. Ein zusätzlicher, bewusst härterer Test (bis 20 Spieler, bis 6 Runden) fand
    weitere, noch nicht lokalisierte Abweichungsfälle (vermutlich in der C10-C21-Kandidatenbewertung,
    nicht mehr in [C8]) - eine ehrlich benannte, noch offene Grenze für eine künftige Vertiefung, aber
    unabhängig von der hier abgeschlossenen [C8]-Arbeit.

**Fünfte Überarbeitung** (Vertiefung der ~2 %-Restlücke): der offizielle bbpPairings-C++-Quellcode
(`src/swisssystems/dutch.cpp`, `src/matching/computer.h`) direkt gelesen, um zu verstehen, WIE die
Referenz-Engine ihre eigenen C6-C21-Kriterien intern zu Kantengewichten kodiert. Ergebnis: die
Restlücke ist tatsächlich EIN klar benennbares Phänomen - echte Gleichstände, bei denen C6, C7 und
C10-C21 (alle bereits implementiert) für mehrere Kandidaten exakt IDENTISCH ausfallen (programmatisch
verifiziert: identische Quality-Tupel für konkurrierende Kandidaten) - bbpPairings löst SOLCHE Reste
aber NICHT über eine einzelne statische Formel, sondern über ein mehrstufiges Neu-Lösen mit gezielt
angepassten Kantengewichten (mehrere `computeMatching()`-Aufrufe je Bracket, dazwischen werden
einzelne Kantengewichte verändert, um Gleichstände deterministisch aufzubrechen). Drei Ansätze
systematisch gegen die echte `bbpPairings.exe` getestet:
- Zwei einfache statische Reihenfolge-Heuristiken für die "welcher gleich bewertete MDP geht in die
  Limbo"-Frage (kanonische Reihenfolge zuerst vs. umgekehrt) - BEIDE gegen eine große
  Zufallsstichprobe gemessen NETTO SCHLECHTER als gar keine Sonderregel (fixten Einzelfälle, brachen
  andere) - verworfen.
- Eine dritte, aus dem bbpPairings-Quellcode abgeleitete Regel ("minimiere zuerst die Anzahl gegenüber
  der besten VOLLEN Paarung aufgegebener MDP-Paare, danach deren BSN-Summe", `_exchange_cost` in
  `ss_bracket.py`) - NETTO KLAR BESSER (fixt deutlich mehr Fälle, als sie bricht), aber auch NICHT
  universell korrekt (mindestens ein Gegenbeispiel gefunden, bei dem bbpPairings genau die nach dieser
  Regel SCHLECHTERE Option wählt) - bewusst behalten, weil messbar positiv, aber ehrlich als
  Heuristik (nicht als hergeleitete Regel) gekennzeichnet.

Beim Debuggen dieser Fälle kam dabei ein GENUIN eigenständiger, klar behebbarer Bug zutage (kein
Gleichstand, sondern eine echte Suchlücke):
13. **`MAX_PER_MDP_PERM` deckelte KANDIDATEN, nicht Downfloater-Stufen**: `_search_homogeneous` liefert
    für eine MDP-Zuordnung erst ALLE Kandidaten der besten (wenigsten Downfloater) Stufe, bevor sie
    reduziert. Hatte allein diese oberste Stufe schon `MAX_PER_MDP_PERM` (3) Varianten (durch mehrere
    Tausch-Kombinationen), wurde die REDUZIERTE Stufe für diese MDP-Zuordnung NIE erreicht - selbst
    wenn genau sie später rundenweit gebraucht wurde, weil die oberste Stufe bracket-lokal perfekt
    aussieht, aber die restliche Runde unlösbar macht. Gefixt: der Deckel zählt jetzt DISTINKTE
    Downfloater-Stufen (mit eigenem Kandidaten-Deckel je Stufe), nicht rohe Kandidaten.

**Gemessenes Endergebnis** (nach Fund 13, `_exchange_cost` behalten): auf den ursprünglichen
Messparametern (4-16 Spieler, 1-4 Runden, jetzt 30 statt 15 Saatwerte für mehr Konfidenz) **98,2 %**
(1401/1427); auf der bewusst härteren Stichprobe (6-19 Spieler, bis 6 Runden, 25 Saatwerte) **92,0 %**
(1835/1994) - beide klar über den vorherigen Messungen (97,8 % bzw. 86,7 % vor dieser Vertiefung).
Performance blieb dabei unerwartet ein eigener Fund: `Player`s berechnete Eigenschaften
(`opponents`, `colour_difference`, `last_two_colours`, ...) liefen als `@property` bei JEDEM Aufruf
neu über `games` - bei Millionen Aufrufen derselben unveränderlichen Spieler-Instanz innerhalb EINER
Rundensuche ein echter, messbarer Kostenfaktor. Umstellung auf `functools.cached_property` (`Player`
ist eine `frozen`-Dataclass, also für die Lebensdauer der Instanz garantiert unveränderlich - reines
Cachen, keine Verhaltensänderung) senkte den schlechtesten beobachteten Fall über 240 Stichproben
(31-32 Spieler, 9 Runden) von ~12 s auf **~1,1 s**, Median von ~0,2 s auf **~0,1 s**.

**Verbliebene, ehrlich benannte Grenze**: echte C6/C7/C10-C21-Gleichstände, die auch nach `_exchange_
cost` noch falsch fallen können - bestätigt nicht durch eine einzelne feste Formel lösbar, sondern nur
durch eine vollständige Portierung von bbpPairings' iterativem Neu-Löse-Mechanismus (deutlich größerer
Umbau, siehe unten "Was diese Demo nicht zeigt"). Zwei Sicherheitsanker (`_matching_fallback`,
`_global_matching_fallback`) garantieren weiterhin [C1]-[C4] in jedem Fall.

- **`ss_bracket.py`**: der eigentliche Suchkern – Transposition/Tausch-Aufzählung (Art. 4.2/4.3), MDP-Auswahl
  für heterogene Brackets (Art. 3.7, 4.4) inklusive M1-Rückfall, liefert Kandidaten lazy in Prioritätsreihenfolge.
- **`ss_quality.py`**: reine Bewertungsfunktionen für C10-C21 je Paar/Spieler – als kleine `int`-Tupel direkt
  vergleichbar (kein Kodiertrick nötig).
- **`ss_engine.py`**: verkettet die Brackets Score-absteigend (Art. 1.9.2), probiert Kandidaten per echter
  Rekursion (Backtracking) statt Heuristik - inklusive [C8] (Art. 2.4.3), das per rekursivem Selbstaufruf
  beliebig TIEF (nicht nur einen Schritt weit) nachprüft, ob die gesamte restliche Kette ohne Reduktion
  durchlöst; ein geteilter Cache verhindert dabei kombinatorische Wiederholung. Teilt danach die Farbe zu
  (`ss_colour.py`, Art. 5.2).
- **`ss_blossom.py`**: übrig geblieben als reine, ungewichtete Kardinalitäts-Existenzprobe – kein gewichtetes
  Matching mehr im Einsatz.

**Verbliebene, ehrlich benannte Grenze**: [C8] schaute lange nur EINE Bracket voraus - das ist geschlossen
(echte, beliebig tiefe Rekursion statt 1-Schritt-Schätzung). Der danach verbliebene Rest ist inzwischen (fünfte
Überarbeitung, s. o.) aus bbpPairings' eigenem Quellcode heraus VERSTANDEN, nicht nur vermutet: echte
Gleichstände zwischen mehreren, nach C6/C7/C10-C21 exakt gleich bewerteten Kandidaten, die die Referenz-Engine
über ein iteratives Neu-Lösen mit angepassten Kantengewichten auflöst - eine einzelne Heuristik dafür
(`_exchange_cost`) hilft messbar (98,2 %/92,0 % statt 97,8 %/86,7 %), ist aber nachweislich nicht in jedem Fall
korrekt. Zwei bewusst schlanke Sicherheitsanker verhindern trotzdem, dass die Suche je fälschlich "unlösbar"
meldet oder eine verbotene Paarung erzeugt: `_matching_fallback` (bipartite Kardinalitäts-Paarung je Bracket)
und `_global_matching_fallback` (rundenweite Paarung als letzter Rettungsanker) - beide garantieren [C1]-[C4],
nicht C6-C21-Optimalität, und greifen nach der aktuellen Messung nur noch in Ausnahmefällen.

**Performance**: die tiefere [C8]-Rekursion machte die Suche zunächst pathologisch langsam für einzelne
Saatwerte (bis 44 s bei 32 Spielern/9 Runden) - nach Memoisierung, dem Fix an `_improve_bye_assignment` und dem
Umstieg von `@property` auf `functools.cached_property` in `ss_model.Player` (s. o., fünfte Überarbeitung)
liegt die gemessene Verteilung über 240 Stichproben (31-32 Spieler, 9 Runden) bei Median **~0,1 s**,
99.-Perzentil ~0,46 s, schlechtester beobachteter Fall **~1,1 s**.

## Was diese Demo (ehrlich) zeigt und was nicht

Die absoluten Kriterien (C1-C3) sind **konstruktiv garantiert**, nicht nur getestet. Die Qualitätskriterien
(C6-C21) stimmen in ~98 % der gemessenen Fälle (98,2 % auf der Standard-, 92,0 % auf einer bewusst härteren
Stichprobe) exakt mit der offiziellen Referenz-Engine überein – die gemessene Quote steht so in App und Tests,
nicht schöngerechnet. Die verbliebene Lücke ist kein unerklärter Rest, sondern ein aus bbpPairings' eigenem
Quellcode verstandenes Phänomen (echte C6-C21-Gleichstände, die ihr eigenes iteratives Neu-Lösen bräuchten, um
IMMER exakt zu treffen) - offen benannt statt verschwiegen, mit einer messbar hilfreichen, aber bewusst als
Heuristik (nicht als hergeleitete Regel) gekennzeichneten Teillösung.

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

- **Kardinalitäts-Existenzprobe**: die verbliebene `ss_blossom.py`-Funktion (nur noch [C4]-Existenzcheck) gegen
  kleine Handbeispiele getestet.
- **Exakte Fixturen**: `dutch_2025_C5`, `dutch_2025_C9` (echte bbpPairings-Testfälle) Zahl für Zahl reproduziert.
- **Eigenschaftstests** über viele Zufallsturniere: C1 nie verletzt (gegen volle Historie), C2 nie zweimal
  Freilos, Rundenkardinalität immer korrekt, Determinismus.
- **Oracle-Cross-Check** (`tests/test_oracle_bbppairings.py`, überspringt sich selbst ohne `BBPPAIRINGS_EXE`):
  Runde 1 für mehrere Feldgrößen exakt, gemessene Gesamt-Übereinstimmungsrate (~98 %, s. o.) mit Sicherheitsmarge
  geprüft.
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
| `ss_quality.py` | Bewertungsfunktionen für C10-C21 je Paar/Spieler |
| `ss_bracket.py` | Transposition/Tausch-Suche je Bracket (Art. 3+4) |
| `ss_blossom.py` | Ungewichtete Kardinalitäts-Existenzprobe für [C4] |
| `ss_engine.py` | Orchestrierung: Brackets Score-absteigend verketten (Art. 1.9.2) |
| `ss_scenario.py` | Turnierfeld + Elo-basierte Simulation |
| `ss_evaluation.py` | Turniertabelle, Kennzahlen |
| `ss_visualization.py` | Plotly: Rundenplan, Turniertabelle, Farbausgleich |
| `ss_oracle_bbppairings.py` | **Nur Tests**: TRF-Schreiber + bbpPairings-Aufruf |
| `tests/` | Existenzproben-Test, Fixturen, Eigenschaftstests, Oracle-Vergleich, Rauchtests |

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
