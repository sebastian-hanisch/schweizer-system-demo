"""Rauchtests der Streamlit-Oberfläche per AppTest: Standard, jedes Preset, Randgrößen."""

from pathlib import Path

import pytest
from streamlit.testing.v1 import AppTest

import ss_constants as C

ROOT = Path(__file__).resolve().parent.parent
APP = ROOT / "app.py"


def _run(setup=None):
    at = AppTest.from_file(str(APP), default_timeout=90)
    at.run()
    assert not at.exception, [e.value for e in at.exception]
    if setup is not None:
        setup(at)
        at.run()
        assert not at.exception, [e.value for e in at.exception]
    return at


def test_default_renders_without_exception():
    at = _run()
    assert any("Wie genau ist die Nachbildung" in h.value for h in at.subheader)


@pytest.mark.parametrize("name", list(C.PRESETS))
def test_every_preset_renders(name):
    p = C.PRESETS[name]

    def setup(at):
        at.session_state["n_players_slider"] = p["n_players"]
        at.session_state["n_rounds_slider"] = p["n_rounds"]
        at.session_state["seed_input"] = p["seed"]

    _run(setup)


def test_extreme_settings_render():
    def small(at):
        at.session_state["n_players_slider"] = C.N_PLAYERS_MIN
        at.session_state["n_rounds_slider"] = C.N_ROUNDS_MIN

    _run(small)

    def large(at):
        at.session_state["n_players_slider"] = C.N_PLAYERS_MAX
        at.session_state["n_rounds_slider"] = C.N_ROUNDS_MAX

    _run(large)


def test_odd_player_count_renders():
    def setup(at):
        at.session_state["n_players_slider"] = 13

    _run(setup)


def test_few_players_many_rounds_shows_early_stop_warning():
    # 4 Spieler, 9 Runden angefragt -> muss vorzeitig abbrechen (C1 erschöpft) und das offen zeigen.
    def setup(at):
        at.session_state["n_players_slider"] = 4
        at.session_state["n_rounds_slider"] = 9

    at = _run(setup)
    assert any("musste nach Runde" in w.value for w in at.warning)
