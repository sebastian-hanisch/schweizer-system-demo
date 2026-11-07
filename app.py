"""Schweizer System (FIDE Dutch System) - interaktive Konzept-Demo
Sebastian Hanisch - Operations Research und Machine Learning

Anders als die Fall-Demos im Portfolio (ein Anwendungsfall, mehrere Verfahren im Vergleich) zeigt diese Demo EIN
Verfahren - das FIDE-Dutch-Paarungssystem für Schweizer-System-Turniere - an einem wachsenden Beispiel. Drittes
Stück der Turnierplanung-Linie der "Konzepte"-Reihe (siehe README für die Einordnung, Stück 1
Rundenturnier und Stück 2 K.-o.-System/Setzliste).

Lauffähig mit: streamlit run app.py
"""

import streamlit as st

import ss_constants as C
from ss_acceleration import accelerated_rounds, group_a_size
from ss_evaluation import max_colour_imbalance, standings, total_byes
from ss_presets import (
    apply_preset,
    bounds,
    init_session_state_defaults,
    load_permalink_settings,
    randomize_seed,
    sync_query_params,
)
from ss_scenario import generate_tournament
from ss_visualization import (
    build_acceleration_table,
    build_colour_balance_chart,
    build_round_table,
    build_standings_table,
)

st.set_page_config(page_title="Schweizer System – Sebastian Hanisch", layout="wide")


@st.cache_data(show_spinner="Turnier wird nach dem echten FIDE-Dutch-Regelwerk gepaart ...")
def _tournament(n_players, n_rounds, seed, engine_mode, baku=False):
    return generate_tournament(n_players, n_rounds, seed, engine_mode=engine_mode, accelerated=baku)


st.title("♟️ Schweizer System (FIDE Dutch System)")
st.markdown(
    """
Das **Schweizer System** löst genau die Schwäche, die das Rundenturnier (Stück 1 dieser Linie) und selbst das
K.-o.-System (Stück 2) nicht ganz auflösen: eine **feste, kleine Rundenzahl**, bei der trotzdem (fast) alle
Teilnehmer viele Partien spielen. Diese Demo baut den Paarungsalgorithmus **nach dem echten FIDE-Regelwerk**
(C.04.3, "Dutch System") nach - alle 21 Kriterien (C1-C21), Farbzuteilung, Freilos-Regeln - und prüft ihn direkt
gegen [bbpPairings](https://github.com/BieremaBoyzProgramming/bbpPairings), die offizielle, FIDE-anerkannte
Referenz-Engine. In der Seitenleiste lässt sich zwischen zwei Paarungs-Engines umschalten - Schritt-für-Schritt
erklärbar nach dem Regeltext, oder exakt nach bbpPairings' eigenem Mechanismus (siehe "Wie genau ist die
Nachbildung wirklich?" unten für den Unterschied). Wer neu im Thema ist, öffnet zuerst „💬 In einfachen Worten“.
"""
)

# erklaerseite:einfach:start (erzeugt von tools/set_demo_explainer.py (Website-Repo) aus tools/content/explainers/schweizer-system-erklaert.json, nicht von Hand ändern)
with st.expander("💬 In einfachen Worten"):
    st.markdown(
        """
Bei vielen Spielern und wenigen Terminen kann nicht jeder gegen jeden spielen. Das Schweizer System löst deshalb in jeder Runde Spieler mit ähnlichem Punktestand gegeneinander aus: Wer gewinnt, trifft auf andere Gewinner, wer verliert, auf andere Verlierer. Dazu kommen feste Regeln: Zwei Spieler treffen nie zweimal aufeinander, die Farben wechseln möglichst ab, und bei einer ungeraden Zahl bekommt einer spielfrei, nie zweimal derselbe.

Die Demo lost zwei Wege aus, einen, der dem Regeltext Schritt für Schritt folgt, und einen, der das offizielle Referenzprogramm nachbaut. Beide wurden in Testläufen mit diesem Programm verglichen. Zusätzlich lässt sich die Baku-Beschleunigung zuschalten, bei der die obere Hälfte der Setzliste in den ersten Runden gedachte Zusatzpunkte bekommt.

[Ausführlich und verständlich erklärt, mit Fachteil](https://sebastianhanisch.net/schweizer-system-erklaert.html)
        """
    )
# erklaerseite:einfach:end
st.caption(
    "Anders als die Fall-Demos im Portfolio, die an einem Anwendungsfall mehrere Verfahren vergleichen, zeigt "
    "diese Demo - drittes Stück der Turnierplanung-Linie der \"Konzepte\"-Reihe - **ein** Verfahren "
    "an einem wachsenden Beispiel: die absoluten Kriterien (C1-C3) gelten hier IMMER exakt, die Feinheiten der "
    "Qualitätskriterien (C6-C21) stimmen auf allen gemessenen Stichproben mit der echten Referenz-Engine überein "
    "(endliche Stichproben, kein Beweis; die Übereinstimmungsrate steht unten, ehrlich gemessen, nicht behauptet)."
)

with st.expander("So funktioniert das Schweizer System (FIDE Dutch)", expanded=True):
    st.markdown(
        r"""
1. **Absolute Kriterien (C1-C3, müssen immer gelten)**: zwei Spieler treffen nie zweimal aufeinander; wer
   schon ein Freilos hatte, bekommt kein zweites; Spieler mit derselben *absoluten* Farbpräferenz treffen
   (außer bei Spitzenreitern) nicht aufeinander.
2. **Bracket für Bracket, wörtlich nach dem Regeltext (Art. 3+4)**: pro Score-Bracket wird zuerst die
   "natürliche" Paarung gebildet (obere Hälfte gegen untere Hälfte in Rangreihenfolge). Erfüllt das nicht alle
   Kriterien, werden Umordnungen (Transposition) und danach Tausche zwischen den beiden Hälften in einer exakt
   vorgegebenen Reihenfolge durchprobiert, bis der erste "perfekte" Kandidat gefunden ist oder alle
   Möglichkeiten erschöpft sind - dann gewinnt der beste bisher gefundene. Nicht gepaarte Spieler floaten in
   die nächste (niedrigere) Bracket.
3. **Farbzuteilung** (Art. 5.2) läuft danach als eigener, deterministischer Schritt: gemeinsame Präferenz
   zuerst, dann die stärkere Einzelpräferenz, dann Alternierung, zuletzt Ranglistenposition.
        """
    )

st.caption("🎯 Schnellstart – ein Beispielszenario laden:")
preset_cols = st.columns(len(C.PRESETS))
for i, name in enumerate(C.PRESETS.keys()):
    with preset_cols[i]:
        st.button(name, width="stretch", on_click=apply_preset, args=(name,), help=C.PRESET_HELP[name])

st.caption(
    "🔗 Die Adresszeile oben spiegelt Ihre aktuelle Konfiguration wider – einfach kopieren, "
    "um ein Szenario zu teilen."
)

load_permalink_settings()
init_session_state_defaults()

with st.sidebar:
    st.header("⚙️ Einstellungen")
    n_players = st.slider("Teilnehmerzahl", *bounds("n_players_slider"), key="n_players_slider")
    n_rounds = st.slider("Rundenzahl", *bounds("n_rounds_slider"), key="n_rounds_slider")
    seed = st.number_input("Zufalls-Seed (Ratings + Partieausgänge)", *bounds("seed_input"), key="seed_input", step=1)
    st.button("🎲 Neues Turnier auslosen", width="stretch", on_click=randomize_seed)

    st.divider()
    st.header("🔀 Paarungs-Engine")
    engine_mode = st.radio(
        "Wie wird gepaart?",
        options=list(C.ENGINE_MODE_LABELS.keys()),
        format_func=lambda k: C.ENGINE_MODE_LABELS[k],
        key="engine_mode_radio",
    )
    st.caption(C.ENGINE_MODE_HELP[engine_mode])

    st.divider()
    st.header("🚀 Beschleunigung")
    baku = st.checkbox("Baku-Beschleunigung (FIDE C.04.7)", key="baku_checkbox", help=C.BAKU_HELP)

sync_query_params(n_players, n_rounds, seed, engine_mode, baku)

n_players, n_rounds, seed = int(n_players), int(n_rounds), int(seed)
tournament = _tournament(n_players, n_rounds, seed, engine_mode, baku)
rows = standings(tournament.players, tournament.ratings)

if len(tournament.rounds) < n_rounds:
    st.warning(
        f"⚠️ Das Turnier musste nach Runde {len(tournament.rounds)} abbrechen: bei diesem kleinen Feld war "
        "keine weitere Paarung mehr möglich, ohne dass zwei Spieler ein zweites Mal aufeinandertreffen "
        "(C1) - ein echter, in der FIDE-Praxis vorkommender Fall, kein Fehler dieser Demo."
    )

st.markdown("---")
st.markdown("## 🎯 Rundenplan")
st.plotly_chart(build_round_table(tournament.rounds), width="stretch", key="round_table")

if baku:
    with st.expander("🚀 Baku-Beschleunigung: wer bekommt wann virtuelle Punkte?", expanded=True):
        st.markdown(
            f"Gruppe **GA** sind die ersten **{min(group_a_size(n_players), n_players)}** von {n_players} Spielern "
            "(obere Hälfte, auf eine gerade Zahl aufgerundet), alle anderen sind **GB**. Beschleunigt werden die "
            f"ersten **{accelerated_rounds(n_rounds)}** von {n_rounds} Runden: GA bekommt vor der ersten Hälfte davon "
            "einen virtuellen Punkt, vor den übrigen einen halben. Gepaart wird nach Tabellenpunkten **plus** "
            "virtuellen Punkten; die Turniertabelle unten zeigt nur die echten Punkte."
        )
        st.plotly_chart(build_acceleration_table(n_players, n_rounds), width="stretch", key="acceleration_table")

st.markdown("## 🎯 Turniertabelle")
group_a_ranks = frozenset(range(1, group_a_size(n_players) + 1)) if baku else None
st.plotly_chart(build_standings_table(rows, group_a_ranks), width="stretch", key="standings")

st.markdown("**Farbausgleich je Spieler**")
st.plotly_chart(build_colour_balance_chart(rows), width="stretch", key="colour_balance")
imbalance = max_colour_imbalance(tournament.players)
byes = total_byes(tournament.rounds)
st.caption(
    f"Größte Weiß/Schwarz-Differenz über alle {n_players} Spieler: **{imbalance}** · "
    f"{byes} Freilose insgesamt über {len(tournament.rounds)} Runden - live geprüft, nicht behauptet."
)

st.markdown("---")

st.subheader("📐 Wie genau ist die Nachbildung wirklich?")
st.markdown(
    """
**Ehrlich gemessen, nicht behauptet**: die absoluten Kriterien (C1-C3, "zwei Spieler treffen nie zweimal
aufeinander" usw.) gelten in **beiden** Modi **beweisbar immer** - eine verbotene Paarung wird nie als
Kandidat gebildet. Für die *Qualitätskriterien* (C6-C21, z. B. "wer floatet, wenn eine Bracket nicht
aufgeht") wurde jede Engine direkt gegen **bbpPairings** (die offizielle, FIDE-anerkannte Referenz-Engine)
auf tausenden zufälligen Testrunden geprüft - die beiden Modi liegen hier bewusst unterschiedlich, s. u.:
"""
)
mc1, mc2 = st.columns(2)
if engine_mode == C.ENGINE_MODE_RULESET:
    mc1.metric("Exakte Übereinstimmung (Qualitätskriterien)", "100 %", help="Gemessen an zufälligen Mehrrundenturnieren, 4-16 Spieler, 1-4 Runden (1430 von 1430 Vergleichen) UND einer bewusst härteren Stichprobe (6-19 Spieler, bis 6 Runden, 1994 von 1994). Auch auf größeren Feldern (8-31 Spieler, 5-9 Runden; 574 von bbpPairings fortgeführte Runden, mit Beschleunigung 576) stimmen Paarung, Freilos und Farben in jeder Runde überein. Das sind endliche Stichproben, kein Beweis. Siehe README für die vollständige Methodik und den Weg dorthin (früher ~99 %/97 %).")
    mc2.metric("Übereinstimmung bei Runde 1 (frisches Feld)", "100 %", help="Die 'obere Hälfte gegen untere Hälfte'-Standardaufteilung wird exakt nachgebildet.")
    st.markdown(
        """
Die Runde wird in zwei Phasen gelöst: Zuerst wird die Kette der Downfloater-Mengen nach [C5]-[C9] bestimmt
([C6]/[C7] je Bracket von oben nach unten, [C8] für den FOLGENDEN Bracket, wie es der Regeltext sagt), erst danach
die Paarungen und Farben ([C10]-[C21]) unter den Paarungen, die zu derselben Menge führen. Die frühere Lücke zur
Referenz-Engine war kein Tie-Break-Problem, sondern eine Reihe von Umsetzungsfehlern: eine Suchbreiten-Grenze, eine zu
strenge Stufenfolge, ein C8, das zu tief schaute, Tauschreihenfolgen nach Rängen statt nach Bracket-Folgenummern und
eine falsche Bewertung ungepaarter MDPs. Auf allen gemessenen Stichproben stimmt dieser Modus jetzt mit bbpPairings
überein - und bleibt trotzdem Schritt für Schritt nachvollziehbar, anders als der bbpPairings-treue Modus."""
    )
else:
    mc1.metric("Exakte Übereinstimmung (Qualitätskriterien)", "100 %", help="Gemessen an zufälligen Mehrrundenturnieren, 4-16 Spieler, 1-4 Runden (1430 Vergleiche) UND einer bewusst härteren Stichprobe (6-19 Spieler, bis 6 Runden, 1994 Vergleiche) - beide exakt 100 %. Auch auf größeren Feldern (8-31 Spieler, 5-9 Runden; 574 von bbpPairings fortgeführte Runden, mit Beschleunigung 576) stimmen Paarung, Freilos und Farben in jeder Runde überein. Siehe README für die vollständige Methodik.")
    mc2.metric("Übereinstimmung bei Runde 1 (frisches Feld)", "100 %", help="Die 'obere Hälfte gegen untere Hälfte'-Standardaufteilung wird in diesem Modus für jede getestete Feldgröße exakt nachgebildet (ab Runde 2 siehe links).")
    st.markdown(
        """
Dieser Modus bildet nicht den FIDE-Regeltext nach, sondern bbpPairings' **eigenen internen Mechanismus**:
EIN einziges gewichtetes Matching-Objekt wird für die GESAMTE Runde (alle Spieler, nicht nur eine Bracket)
einmal angelegt und dann bracket-für-bracket mit inkrementell angepassten Kantengewichten weitergelöst -
direkt aus dem geklonten `bbpPairings`-Quellcode portiert (`computeEdgeWeight`, `dutch.cpp`) und gegen die
Referenz-Engine verifiziert. Beide Modi stimmen auf allen gemessenen Stichproben mit der Referenz überein; der Unterschied liegt in der Erklärbarkeit:
die einzelne Paarungsentscheidung ("warum spielt X gegen Y") ist hier NICHT in einzelne, für sich nachvollziehbare
Regelschritte zerlegbar wie im Regeltext-Modus, sondern das Ergebnis eines globalen Optimierungslaufs. Das ist kein
"besser" oder "schlechter" an sich."""
    )

st.markdown("---")

with st.expander("📐 Mathematische Formulierung"):
    # erklaerseite:lesehilfe:start (erzeugt von tools/set_demo_explainer.py (Website-Repo) aus tools/content/explainers/schweizer-system-erklaert.json, nicht von Hand ändern)
    st.markdown(
        r"""
**Lesehilfe.** Gegeben sind $N$ Spieler mit Wertungszahlen, $R$ geplante Runden und ein bisheriger Punktestand $s_i$. Gesucht ist in jeder Runde eine Paarung, die die Regeln des FIDE Dutch Systems erfüllt; verglichen wird sie mit der Auslosung des Referenzprogramms bbpPairings.

| Symbol | Bedeutung |
|---|---|
| $N$, $R$ | Zahl der Spieler und der geplanten Runden |
| $s_i$ | echter Punktestand des Spielers $i$ |
| $G_A$ | obere Hälfte der Setzliste (Gruppe der Baku-Beschleunigung) |
| $a$ | Zahl der beschleunigten Runden |
| $v_r$ | gedachte Zusatzpunkte der Gruppe $G_A$ vor Runde $r$ |
| $R_A$, $R_B$ | Wertungszahlen zweier Spieler in der Simulation |
| $E_A$ | erwarteter Punktanteil von $A$ gegen $B$ |

[Schritt für Schritt erklärt, mit Herleitung und Literatur](https://sebastianhanisch.net/schweizer-system-erklaert.html#fachleute)
        """
    )
    # erklaerseite:lesehilfe:end
    st.markdown(
        r"""
**Modell.** Eine Runde wird **Bracket für Bracket** gelöst (Score absteigend, Art. 1.9.2) - keine
Neuformulierung als ein einziges globales Matching, sondern die im Regeltext selbst vorgeschriebene
Prozedur (Art. 3+4): pro Bracket wird eine Menge $S_1$ (die ersten $N_1$ Spieler nach Rang) gegen $S_2$
(die restlichen) paarungskandidaten gebildet, $S_1[i]$ gegen $S_2[i]$. Erfüllt dieser Kandidat nicht alle
Kriterien, werden Umordnungen $\pi$ von $S_2$ (Transpositionen) und danach Tausche gleich großer Gruppen
zwischen $S_1$ und $S_2$ durchprobiert. Statt nur den lokal besten Kandidaten je Bracket zu schätzen, liefert
die Suche die brauchbaren Kandidaten in Prioritätsreihenfolge (Art. 3.8.1). Welche Menge von Spielern aus einer
Bracket herausfällt, entscheidet vorab eine Kette über alle Brackets ([C5]-[C9], dynamische Programmierung mit
Matching-Test, `ss_chain.py`); die Kandidatenliste mit Farbbewertung wird nur noch einmal je Bracket entlang des
gewählten Wegs gelesen. Jedes Kriterium
$C_{10}, ..., C_{21}$ ist dabei eine eigenständige, kleine ganze Zahl - der Vergleich ist ein direkter
lexikografischer Tupel-Vergleich, kein gemischt-radix-Kodiertrick nötig.

**Warum nicht (nur) ein globales Matching?** Eine frühere Fassung dieser Demo löste die ganze Runde als EIN
gewichtetes allgemeines Matching (wie [`weighted-blossom-demo`](https://github.com/sebastian-hanisch/weighted-blossom-demo)),
weil die Referenz-Engine bbpPairings das intern so tut - erreichte damals aber nur ~66 % Übereinstimmung, weil
es eine grobe Annäherung an bbpPairings' Implementierungsstrategie war, nicht deren treue Nachbildung. Die
direkte Umsetzung von Art. 3+4 (Transposition/Tausch statt globalem Matching) mit echtem Backtracking hob die
Übereinstimmung auf ~99 %/97 %; weitere Korrekturen (Details im README) bringen den **Regeltext-Modus** hier auf allen
gemessenen Stichproben auf 100 %. Er bleibt der Standard, weil jeder Schritt einzeln nachvollziehbar bleibt (der
pädagogische Kern dieser Demo). Der **bbpPairings-treue Modus** (⚙️ Einstellungen) ist der vollständige Nachbau von
bbpPairings' eigenem Mechanismus, ein einziges rundenweit fortgeführtes gewichtetes Matching-Objekt, ebenfalls mit
100 % - auf Kosten der Nachvollziehbarkeit einzelner Paarungsentscheidungen, s.
"Wie genau ist die Nachbildung wirklich?" oben.

**Elo-Erwartungswert** (Simulation der Turnierverläufe): $E_A = 1/(1+10^{(R_B-R_A)/400})$.

**Baku-Beschleunigung** (FIDE C.04.7). Bei $N$ Spielern und $R$ Runden bilden die ersten Spieler der Setzliste die Gruppe $G_A$, die obere Hälfte
aufgerundet auf eine gerade Zahl:

$$|G_A| = 2\left\lceil N/4 \right\rceil$$

Beschleunigt werden die ersten $a = \lceil R/2 \rceil$ Runden. Vor der ersten Hälfte davon bekommt $G_A$ einen gedachten Punkt, vor den übrigen
beschleunigten Runden einen halben, danach nichts; gepaart wird nach $s_i + v_r$ für $i \in G_A$:

$$v_r = 1 \ (r \le \lceil a/2 \rceil), \quad v_r = 1/2 \ (\lceil a/2 \rceil < r \le a), \quad v_r = 0 \ (r > a), \qquad a = \lceil R/2 \rceil$$

Regeltext-Modus implementiert in `ss_engine.py` (Runde vorbereiten, Farben), `ss_chain.py` (Kette der Downfloater-
Mengen nach C5-C9), `ss_bracket.py` (Transposition/Tausch-Suche) und `ss_quality.py` (Kriterien C10-C21); bbpPairings-treuer Modus in `ss_matching_engine.py` (ein
einziges rundenweites Matching-Objekt) - beide nutzen `ss_colour.py` (Farbzuteilung) gemeinsam.
        """
    )

st.markdown("---")

st.caption(
    "Diese Demo ist Teil des Portfolios von [Sebastian Hanisch](https://sebastianhanisch.net) – "
    "Operations Research und Machine Learning ([Über mich](https://sebastianhanisch.net/ueber-mich.html)). "
    "Mehr zur Reihe: [Turnierplanung: 7 Wege zum Turnierplan](https://sebastianhanisch.net/konzepte-turnierplanung.html)."
)
