"""NUR FÜR TESTS: TRF-Schreiber + Aufruf der vendorten `bbpPairings`-Programmdatei (offizielle
FIDE-anerkannte Referenz-Engine) + Ausgabe-Parser. Wird nie von `app.py`/`ss_engine.py` importiert.

Das TRF-Spaltenformat wurde NICHT aus der Spezifikation abgetippt, sondern direkt aus den
mitgelieferten bbpPairings-Testfixturen (`test/tests/dutch_2025_C5.input` etc.) durch Byte-Position
zurückgewonnen und gegen die echte `bbpPairings.exe` verifiziert (Round-Trip-Test bestanden) - Name/
Rating/Titel-Felder sind für die Dutch-Paarung irrelevant und werden mit einem festen Platzhalter
gefüllt, nur Rang, Score, Gegner/Farbe/Ergebnis je Runde sind echt.
"""

from __future__ import annotations

import os
import subprocess
from pathlib import Path

from ss_model import BYE, Player

_CONST_SUFFIX = "      Test0001 Player0001               2720                            "  # 72 Zeichen


def _player_line(rank: int, score: float, rounds: list[tuple[int, str | None, str]]) -> str:
    s = "001 " + f"{rank:>4}" + _CONST_SUFFIX
    s += f"{score:>4.1f}"
    s += f"{rank:>5}"
    for opp, colour, result in rounds:
        c = colour if colour is not None else "-"
        opp_field = "  0000" if opp == 0 else f"{opp:>6}"  # Freilos: literal "0000", nicht rechtsbündiges "0"
        s += f"{opp_field} {c} {result}"
    return s


def write_trf(players: dict[int, Player], next_round: int, absent: frozenset[int] = frozenset()) -> str:
    lines = ["012 Cross-Check"]
    any_colour_history = any(g.colour is not None for p in players.values() for g in p.games)
    for rank in sorted(players):
        p = players[rank]
        rounds = []
        for g in p.games:
            if g.opponent == BYE:
                result = "Z" if g.score == 0.0 else ("H" if g.score == 0.5 else "U")
                rounds.append((0, None, result))
            else:
                result = "1" if g.score == 1.0 else ("=" if g.score == 0.5 else "0")
                rounds.append((g.opponent, g.colour, result))
        if rank in absent:
            rounds.append((0, None, "Z"))
        lines.append(_player_line(rank, p.score, rounds))
    if not any_colour_history:
        # Ohne jede Farbhistorie verlangt bbpPairings eine explizite Anfangsfarben-Regel (siehe
        # src/fileformats/trf.cpp, Direktive "XXC white1") - sonst Parse-Fehler.
        lines.append("XXC white1")
    lines.append(f"XXR {next_round}")
    return "\n".join(lines) + "\n"


class BbpPairingsUnavailable(RuntimeError):
    pass


def _find_exe() -> Path | None:
    env_path = os.environ.get("BBPPAIRINGS_EXE")
    if env_path and Path(env_path).is_file():
        return Path(env_path)
    return None


def run_bbppairings(players: dict[int, Player], next_round: int, absent: frozenset[int] = frozenset(), *, exe_path: str | None = None) -> tuple[list[tuple[int, int]], int | None]:
    """Gibt (Paare, Freilos) zurück - Paare als (weiss, schwarz) Ranglisten-Nummern. Wirft
    `BbpPairingsUnavailable`, wenn die Programmdatei nicht gefunden wird (z. B. offline, kein Netz
    zum Herunterladen) - Aufrufer sollte den Test dann überspringen (skipif), nicht fehlschlagen."""
    exe = Path(exe_path) if exe_path else _find_exe()
    if exe is None or not exe.is_file():
        raise BbpPairingsUnavailable("bbpPairings-Programmdatei nicht gefunden (BBPPAIRINGS_EXE setzen)")

    trf_text = write_trf(players, next_round, absent)
    import tempfile

    with tempfile.TemporaryDirectory() as tmp:
        in_path = Path(tmp) / "cross.trf"
        out_path = Path(tmp) / "cross.out"
        in_path.write_text(trf_text, encoding="ascii")
        proc = subprocess.run(
            [str(exe), "--dutch", str(in_path), "-p", str(out_path)],
            capture_output=True, text=True, timeout=30,
        )
        if proc.returncode != 0:
            raise RuntimeError(f"bbpPairings exit={proc.returncode}: {proc.stderr.strip()}")
        out_text = out_path.read_text(encoding="ascii")

    lines = [ln.strip() for ln in out_text.splitlines() if ln.strip()]
    n_entries = int(lines[0])  # Paare UND Freilos zusammen, nicht nur Paare
    pairs: list[tuple[int, int]] = []
    bye: int | None = None
    for line in lines[1:]:
        a, b = (int(x) for x in line.split())
        if b == 0:
            bye = a
        else:
            pairs.append((a, b))
    assert len(pairs) + (1 if bye is not None else 0) == n_entries, (
        f"erwartet {n_entries} Einträge, bekommen {pairs} (bye={bye}); trf=\n{trf_text}"
    )
    return pairs, bye
