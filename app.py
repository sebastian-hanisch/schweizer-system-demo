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
aufeinander" usw.) gelten in dieser Demo **beweisbar immer** - eine verbotene Paarung wird nie als Kandidat
gebildet. Für die *Qualitätskriterien* (C6-C21, z. B. "wer floatet, wenn eine Bracket nicht aufgeht") wurde die
Engine direkt gegen **bbpPairings** (die offizielle, FIDE-anerkannte Referenz-Engine) auf hunderten zufälligen
Testrunden geprüft:
"""
)
mc1, mc2 = st.columns(2)
mc1.metric("Exakte Übereinstimmung (Qualitätskriterien)", "~98 %", help="Gemessen an zufälligen Mehrrundenturnieren, 4-16 Spieler, 1-4 Runden (1427 Vergleiche) - auf einer bewusst härteren Stichprobe (6-19 Spieler, bis 6 Runden) ~92 %. Siehe README für die vollständige Methodik.")
mc2.metric("Übereinstimmung bei Runde 1 (frisches Feld)", "100 %", help="Die 'obere Hälfte gegen untere Hälfte'-Standardaufteilung wird exakt nachgebildet.")
st.markdown(
    """
Die eingebaute Vorausschau ([C8], "erreicht die nächste Bracket ihr eigenes Maximum?") prüft per echter,
beliebig tiefer Rekursion die GESAMTE restliche Kette, nicht nur den nächsten Schritt. Der Rest der Abweichung
wurde direkt aus bbpPairings' eigenem Quellcode heraus untersucht: es sind echte Gleichstände zwischen mehreren,
nach allen 21 Kriterien exakt gleich bewerteten Kandidaten - die Referenz-Engine löst SOLCHE Reste über ein
mehrstufiges Neu-Lösen mit angepassten Kantengewichten, nicht über eine einzelne feste Regel. Eine aus diesem
Mechanismus abgeleitete Heuristik hilft messbar (98,2 %/92,0 % statt 97,8 %/86,7 % vorher), ist aber
nachweislich nicht in jedem Einzelfall korrekt - offen ausgewiesen, keine verschwiegene Lücke.
"""
)

st.markdown("---")

with st.expander("📐 Mathematische Formulierung"):
    st.markdown(
        r"""
**Modell.** Eine Runde wird **Bracket für Bracket** gelöst (Score absteigend, Art. 1.9.2) - keine
Neuformulierung als ein einziges globales Matching, sondern die im Regeltext selbst vorgeschriebene
Prozedur (Art. 3+4): pro Bracket wird eine Menge $S_1$ (die ersten $N_1$ Spieler nach Rang) gegen $S_2$
(die restlichen) paarungskandidaten gebildet, $S_1[i]$ gegen $S_2[i]$. Erfüllt dieser Kandidat nicht alle
Kriterien, werden Umordnungen $\pi$ von $S_2$ (Transpositionen) und danach Tausche gleich großer Gruppen
zwischen $S_1$ und $S_2$ durchprobiert. Statt nur den lokal besten Kandidaten je Bracket zu schätzen, liefert
die Suche ALLE brauchbaren Kandidaten in Prioritätsreihenfolge (Art. 3.8.1) - die Rundenlösung probiert für
jeden per echter Rekursion, ob sich die restliche Runde damit zu Ende lösen lässt (**echtes Backtracking**
statt einer Schätzung), und geht erst bei Fehlschlag zum nächsten Kandidaten über. Jedes Kriterium
$C_{10}, ..., C_{21}$ ist dabei eine eigenständige, kleine ganze Zahl - der Vergleich ist ein direkter
lexikografischer Tupel-Vergleich, kein gemischt-radix-Kodiertrick nötig.

**Warum nicht ein globales Matching?** Eine frühere Fassung dieser Demo löste die ganze Runde als EIN
gewichtetes allgemeines Matching (wie [`weighted-blossom-demo`](https://github.com/sebastian-hanisch/weighted-blossom-demo)),
weil die Referenz-Engine bbpPairings das intern so tut. Das erreichte ~66 % Übereinstimmung mit bbpPairings,
war aber eine Nachbildung von bbpPairings' eigener Implementierungsstrategie, nicht des FIDE-Regeltexts
selbst. Die direkte Umsetzung von Art. 3+4 (Transposition/Tausch statt globalem Matching) mit echtem
Backtracking hob die Übereinstimmung auf ~98 % - siehe README für die vollständige Herleitung. Für die
verbliebene ~2-8 %-Lücke (echte Gleichstände) wurde bbpPairings' Quellcode noch einmal gezielt gelesen, um NUR
das Grundprinzip eines EINZELNEN Tie-Break-Kriteriums (`_exchange_cost`) zu übernehmen - die Bracket-für-
Bracket-Architektur nach Art. 3+4 bleibt dabei die tragende Suche, kein Rückbau zum globalen Matching.

**Elo-Erwartungswert** (Simulation der Turnierverläufe): $E_A = 1/(1+10^{(R_B-R_A)/400})$.

Implementiert in `ss_engine.py` (Bracket-Verkettung), `ss_bracket.py` (Transposition/Tausch-Suche),
`ss_quality.py` (Kriterien C10-C21) und `ss_colour.py` (Farbzuteilung).
        """
    )

st.markdown("---")

st.caption(
    "Diese Demo ist Teil des Portfolios von [Sebastian Hanisch](https://sebastianhanisch.net) – "
    "Operations Research und Machine Learning. Interesse an einer maßgeschneiderten Lösung für "
    "Ihr Unternehmen? [Kontakt aufnehmen](https://sebastianhanisch.net/kontakt.html)"
)
