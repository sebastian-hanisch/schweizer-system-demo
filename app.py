"""Schweizer System (FIDE Dutch System) - interaktive Konzept-Demo
Sebastian Hanisch - Operations Research und Machine Learning

Anders als die Fall-Demos im Portfolio (ein Anwendungsfall, mehrere Verfahren im Vergleich) zeigt diese Demo EIN
Verfahren - das FIDE-Dutch-Paarungssystem für Schweizer-System-Turniere - an einem wachsenden Beispiel. Drittes
und letztes Stück der Turnierplanung-Linie der "Konzepte"-Reihe (siehe README für die Einordnung, Stück 1
Rundenturnier und Stück 2 K.-o.-System/Setzliste).

Lauffähig mit: streamlit run app.py
"""

import streamlit as st

import ss_constants as C
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
from ss_visualization import build_colour_balance_chart, build_round_table, build_standings_table

st.set_page_config(page_title="Schweizer System – Sebastian Hanisch", layout="wide")


@st.cache_data(show_spinner="Turnier wird nach dem echten FIDE-Dutch-Regelwerk gepaart ...")
def _tournament(n_players, n_rounds, seed):
    return generate_tournament(n_players, n_rounds, seed)


st.title("♟️ Schweizer System (FIDE Dutch System)")
st.markdown(
    """
Das **Schweizer System** löst genau die Schwäche, die das Rundenturnier (Stück 1 dieser Linie) und selbst das
K.-o.-System (Stück 2) nicht ganz auflösen: eine **feste, kleine Rundenzahl**, bei der trotzdem (fast) alle
Teilnehmer viele Partien spielen. Diese Demo baut den Paarungsalgorithmus **nach dem echten FIDE-Regelwerk**
(C.04.3, "Dutch System") nach - alle 21 Kriterien (C1-C21), Farbzuteilung, Freilos-Regeln - und prüft ihn direkt
gegen [bbpPairings](https://github.com/BieremaBoyzProgramming/bbpPairings), die offizielle, FIDE-anerkannte
Referenz-Engine.
"""
)
st.caption(
    "Anders als die Fall-Demos im Portfolio, die an einem Anwendungsfall mehrere Verfahren vergleichen, zeigt "
    "diese Demo - drittes und letztes Stück der Turnierplanung-Linie der \"Konzepte\"-Reihe - **ein** Verfahren "
    "an einem wachsenden Beispiel: die absoluten Kriterien (C1-C3) gelten hier IMMER exakt, die Feinheiten der "
    "Qualitätskriterien (C6-C21) sind eine gute Näherung mit einer ehrlich gemessenen, nicht behaupteten "
    "Übereinstimmungsrate gegenüber der echten Referenz-Engine."
)

with st.expander("So funktioniert das Schweizer System (FIDE Dutch)", expanded=True):
    st.markdown(
        r"""
1. **Absolute Kriterien (C1-C3, müssen immer gelten)**: zwei Spieler treffen nie zweimal aufeinander; wer
   schon ein Freilos hatte, bekommt kein zweites; Spieler mit derselben *absoluten* Farbpräferenz treffen
   (außer bei Spitzenreitern) nicht aufeinander.
2. **Die ganze Runde als ein gewichtetes Matching**: statt Bracket für Bracket nacheinander zu entscheiden,
   wird die komplette Runde auf einmal gelöst - ein Knoten je Spieler, plus ein virtueller Freilos-Knoten bei
   ungerader Teilnehmerzahl. Jede zulässige Paarung ist eine Kante, ihr Gewicht kodiert alle Kriterien C5-C21
   in absteigender Priorität als eine einzige Zahl (höchste Priorität = signifikanteste Stelle). Der
   [gewichtete Blossom-Algorithmus](https://github.com/sebastian-hanisch/weighted-blossom-demo) (Edmonds,
   bereits an anderer Stelle dieses Portfolios gebaut) findet das beweisbar beste Matching dazu.
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

sync_query_params(n_players, n_rounds, seed)

n_players, n_rounds, seed = int(n_players), int(n_rounds), int(seed)
tournament = _tournament(n_players, n_rounds, seed)
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

st.markdown("## 🎯 Turniertabelle")
st.plotly_chart(build_standings_table(rows), width="stretch", key="standings")

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
aufeinander" usw.) gelten in dieser Demo **beweisbar immer** - dafür sorgt die Konstruktion des Matchings selbst
(eine verbotene Paarung existiert als Kante schlicht nicht). Für die *Qualitätskriterien* (C6-C21, z. B. "wer
floatet, wenn eine Bracket nicht aufgeht") wurde die Engine direkt gegen **bbpPairings** (die offizielle,
FIDE-anerkannte Referenz-Engine) auf hunderten zufälligen Testrunden geprüft:
"""
)
mc1, mc2 = st.columns(2)
mc1.metric("Exakte Übereinstimmung (Qualitätskriterien)", "~66 %", help="Gemessen an zufälligen Mehrrundenturnieren, 4-10 Spieler, 1-3 Runden - siehe README für die vollständige Methodik.")
mc2.metric("Übereinstimmung bei Runde 1 (frisches Feld)", "100 %", help="Die 'obere Hälfte gegen untere Hälfte'-Standardaufteilung wird exakt nachgebildet.")
st.markdown(
    """
Der Rest der Abweichung liegt an bbpPairings' eigener, nicht dokumentierter interner Gewichtsstaffelung für die
Tie-Breaks innerhalb der Qualitätskriterien, die sich aus der reinen Regeltext-Lektüre nicht vollständig
rekonstruieren ließ - mehrere konkrete Hypothesen wurden getestet und wieder verworfen, weil sie den Abgleich
nicht verbesserten. Das ist eine bewusste, offen ausgewiesene Grenze dieser Demo, keine verschwiegene.
"""
)

st.markdown("---")

with st.expander("📐 Mathematische Formulierung"):
    st.markdown(
        r"""
**Modell.** Eine Runde ist ein **gewichtetes perfektes Matching** über den Graphen $G=(V,E)$, $V$ = aktive
Spieler (plus ein virtueller Freilos-Knoten bei ungerader Anzahl), $E$ = alle Paare, die C1 (keine Wiederholung)
und C3 (keine absolute Farbkollision) erfüllen. Jede Kante $(i,j)$ trägt ein Gewicht

$$
w(i,j) = \sum_{k} t_k(i,j) \cdot \text{BASIS}^{n-1-k},
$$

eine gemischt-radix-Kodierung der Kriterien C5-C21 in absteigender Priorität (höchste Priorität = größte
Potenz von BASIS). Da BASIS größer ist als jeder einzelne Term, dominiert jede höherprioritäre Stelle
JEDE mögliche Kombination aller niedrigeren Stellen zusammen - das gewichtsmaximale Matching ist damit
automatisch lexikografisch optimal in den kodierten Kriterien.

**Warum ein Matching-Algorithmus?** Das Paarungsproblem ist strukturell ein **allgemeines** (nicht bipartites)
Graphenproblem - jeder Spieler kann mit jedem anderen kompatiblen Spieler zusammentreffen, nicht nur zwischen
zwei festen Gruppen. Der [Edmonds-Blossom-Algorithmus](https://github.com/sebastian-hanisch/weighted-blossom-demo)
(1965, hier mit Galils primal-dualer Methode) ist das Standardverfahren dafür und liefert ein bewiesenes Optimum,
keine Heuristik.

**Elo-Erwartungswert** (Simulation der Turnierverläufe): $E_A = 1/(1+10^{(R_B-R_A)/400})$.

Implementiert in `ss_engine.py` (Orchestrierung), `ss_weights.py` (Kriterien-Kodierung), `ss_blossom.py`
(Matching-Kern) und `ss_colour.py` (Farbzuteilung).
        """
    )

st.markdown("---")

st.caption(
    "Diese Demo ist Teil des Portfolios von [Sebastian Hanisch](https://sebastianhanisch.net) – "
    "Operations Research und Machine Learning. Interesse an einer maßgeschneiderten Lösung für "
    "Ihr Unternehmen? [Kontakt aufnehmen](https://sebastianhanisch.net/kontakt.html)"
)
