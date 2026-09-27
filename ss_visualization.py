"""Plotly-Visualisierungen: Rundenplan-Tabelle, Turniertabelle, Farbausgleich.
Alle Figuren laufen durch `lock_axes` (Touch-Scrolling-Konvention des Portfolios)."""

from __future__ import annotations

import plotly.graph_objects as go

from ss_evaluation import StandingsRow
from ss_model import RoundResult

NAVY = "#14233B"
ORANGE = "#d68a2e"
BLUE = "#1f77b4"
GRAY = "#8a8f98"


def build_round_table(rounds: tuple[RoundResult, ...]) -> go.Figure:
    n_rounds = len(rounds)
    header = ["Runde"] + [f"R{r.round_no}" for r in rounds]
    max_lines = max((len(r.pairings) + (1 if r.bye else 0) for r in rounds), default=1)
    columns = [[str(i + 1) for i in range(max_lines)]]
    for r in rounds:
        lines = [f"{p.white}(W) – {p.black}(S)" for p in r.pairings]
        if r.bye is not None:
            lines.append(f"{r.bye}: Freilos")
        lines += [""] * (max_lines - len(lines))
        columns.append(lines)
    fig = go.Figure(
        data=[go.Table(header=dict(values=header, fill_color=NAVY, font=dict(color="white"), align="center"), cells=dict(values=columns, align="center", height=26))]
    )
    fig.update_layout(margin=dict(l=0, r=0, t=0, b=0), height=min(120 + max_lines * 28, 700))
    return fig


def build_standings_table(rows: list[StandingsRow]) -> go.Figure:
    header = ["Platz", "Rang", "Rating", "Score", "Weiß", "Schwarz", "Freilose"]
    columns = [
        [str(i + 1) for i in range(len(rows))],
        [str(r.rank) for r in rows],
        [f"{r.rating:.0f}" for r in rows],
        [f"{r.score:.1f}" for r in rows],
        [str(r.white_games) for r in rows],
        [str(r.black_games) for r in rows],
        [str(r.byes) for r in rows],
    ]
    fig = go.Figure(
        data=[go.Table(header=dict(values=header, fill_color=NAVY, font=dict(color="white"), align="center"), cells=dict(values=columns, align="center", height=26))]
    )
    fig.update_layout(margin=dict(l=0, r=0, t=0, b=0), height=min(120 + len(rows) * 26, 700))
    return fig


def build_colour_balance_chart(rows: list[StandingsRow]) -> go.Figure:
    ranks = [r.rank for r in rows]
    fig = go.Figure()
    fig.add_trace(go.Bar(x=ranks, y=[r.white_games for r in rows], name="Weiß", marker_color=ORANGE))
    fig.add_trace(go.Bar(x=ranks, y=[-r.black_games for r in rows], name="Schwarz", marker_color=NAVY))
    fig.update_layout(
        template="plotly_white",
        barmode="relative",
        height=300,
        margin=dict(l=10, r=10, t=20, b=10),
        legend=dict(orientation="h", y=-0.2),
    )
    fig.update_xaxes(title="Startranglisten-Nummer", dtick=1, fixedrange=True)
    fig.update_yaxes(title="Weiß-Partien (oben) / Schwarz-Partien (unten)", fixedrange=True)
    return fig
