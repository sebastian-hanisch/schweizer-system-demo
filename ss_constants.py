"""Regler-Grenzen, Presets und Konstanten für die Schweizer-System-Demo."""

DEFAULT_N_PLAYERS = 16
N_PLAYERS_MIN, N_PLAYERS_MAX = 4, 32

DEFAULT_N_ROUNDS = 5
N_ROUNDS_MIN, N_ROUNDS_MAX = 1, 9

DEFAULT_SEED = 1
DEFAULT_WIN_PROB = 0.55  # P(höher gesetzter Spieler gewinnt) im Simulationsmodell

# --- Presets -----------------------------------------------------------------
_BASE = {"n_players": DEFAULT_N_PLAYERS, "n_rounds": DEFAULT_N_ROUNDS, "seed": DEFAULT_SEED}
PRESETS = {
    "Kleines Vereinsturnier (12 Spieler, 5 Runden)": {**_BASE, "n_players": 12, "n_rounds": 5},
    "Ungerade Teilnehmerzahl (13 Spieler, mit Freilosen)": {**_BASE, "n_players": 13, "n_rounds": 5},
    "Größeres Open (32 Spieler, 7 Runden)": {**_BASE, "n_players": 32, "n_rounds": 7},
    "Nur 3 Runden (viele Gleichstände am Ende)": {**_BASE, "n_players": 16, "n_rounds": 3},
}
PRESET_HELP = {
    "Kleines Vereinsturnier (12 Spieler, 5 Runden)": "Der Standardfall: 12 Spieler, 5 Runden - typische Vereinsmeisterschaft.",
    "Ungerade Teilnehmerzahl (13 Spieler, mit Freilosen)": "Bei ungerader Teilnehmerzahl bekommt jede Runde ein Spieler ein Freilos (C2: nie zweimal derselbe).",
    "Größeres Open (32 Spieler, 7 Runden)": "32 Spieler brauchen bei einem Rundenturnier 31 Runden - hier reichen 7, der ganze Punkt des Schweizer Systems.",
    "Nur 3 Runden (viele Gleichstände am Ende)": "Wenige Runden bei vielen Spielern: am Ende teilen sich mehrere Spieler denselben Score - die Bracket-Bildung zeigt das deutlich.",
}
