"""SETTING_SPECS-Permalink-Muster und Presets (Standardmuster aus dem OR-Demo-Portfolio, s. pca_presets.py)."""

import math
import random
from dataclasses import dataclass
from typing import Callable, Optional

import streamlit as st

import ss_constants as C


@dataclass(frozen=True)
class SettingSpec:
    url_param: str
    caster: Callable
    default: object
    lo: Optional[float] = None
    hi: Optional[float] = None


SETTING_SPECS = {
    "n_players_slider": SettingSpec("n", int, C.DEFAULT_N_PLAYERS, C.N_PLAYERS_MIN, C.N_PLAYERS_MAX),
    "n_rounds_slider": SettingSpec("rounds", int, C.DEFAULT_N_ROUNDS, C.N_ROUNDS_MIN, C.N_ROUNDS_MAX),
    "seed_input": SettingSpec("seed", int, C.DEFAULT_SEED, 0, 2_000_000_000),
}


def bounds(state_key):
    spec = SETTING_SPECS[state_key]
    return spec.lo, spec.hi


def init_session_state_defaults():
    for state_key, spec in SETTING_SPECS.items():
        if state_key not in st.session_state:
            st.session_state[state_key] = spec.default


def load_permalink_settings():
    if "permalink_loaded" in st.session_state:
        return
    qp = st.query_params
    for state_key, spec in SETTING_SPECS.items():
        if spec.url_param in qp:
            try:
                value = spec.caster(qp[spec.url_param])
                if isinstance(value, float) and not math.isfinite(value):
                    continue
                if spec.lo is not None:
                    value = max(spec.lo, value)
                if spec.hi is not None:
                    value = min(spec.hi, value)
                st.session_state[state_key] = value
            except (ValueError, TypeError):
                pass
    st.session_state["permalink_loaded"] = True


def sync_query_params(n_players, n_rounds, seed):
    try:
        st.query_params["n"] = str(int(n_players))
        st.query_params["rounds"] = str(int(n_rounds))
        st.query_params["seed"] = str(int(seed))
    except Exception:
        pass


def apply_preset(name):
    p = C.PRESETS[name]
    st.session_state["n_players_slider"] = p["n_players"]
    st.session_state["n_rounds_slider"] = p["n_rounds"]
    st.session_state["seed_input"] = p["seed"]


def randomize_seed():
    st.session_state["seed_input"] = random.randint(0, 2_000_000_000)
