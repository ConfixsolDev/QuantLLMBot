"""Strict configuration loader for the structure engine.

RULE 3 of Module 1: *no hard-coded thresholds*. Every number a detector uses
comes from a versioned JSON file (``config/xauusd_structure_v1.json``), and

* an UNKNOWN key fails at load time  (catches typos like ``"max_tset"``),
* a MISSING key fails at load time   (no silent defaults hiding in code),
* a value of the WRONG TYPE fails     (``"14"`` is not ``14``),
* the whole config is fingerprinted   (``config_hash``) and that hash is
  stamped on every event, so any result can be traced to the exact numbers
  that produced it. Change one threshold -> new hash -> results are not pooled.

The schema below is the single list of every tunable. To add a threshold:
add it to the JSON *and* to ``SCHEMA``; the loader refuses one without the
other.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

#: The config shipped with the package. Pass another path to load_config()
#: to experiment; the hash keeps experiments apart.
DEFAULT_CONFIG = Path(__file__).resolve().parent / "config" / "xauusd_structure_v1.json"

# --------------------------------------------------------------------------
# Schema markers. A schema is a nested dict whose leaves describe the value:
#   INT / NUM / STR      a single int, number (int or float) or string
#   POS_INT / POS_NUM    strictly positive int / number
#   TF                   one timeframe name declared in "timeframes"
#   TF_LIST              list of timeframe names declared in "timeframes"
#   INT_LIST             non-empty list of ints
#   BOOL                 true / false
#   ("tfmap", LEAF)      dict keyed by declared timeframe names
#   ("map", LEAF)        dict with free string keys (e.g. session names)
#   ("pair", LEAF)       two-element list
#   ("list", LEAF)       non-empty list
# --------------------------------------------------------------------------
INT, NUM, STR, POS_INT, POS_NUM, TF_LIST, TF, INT_LIST, BOOL = (
    "int", "num", "str", "pos_int", "pos_num", "tf_list", "tf", "int_list", "bool")

SCHEMA: dict[str, Any] = {
    "config_id": STR,
    "symbol": STR,
    "timeframes": ("map", POS_INT),           # name -> minutes; must include M1 = 1
    "alignment": ("tfmap", {"source": TF, "timezone": STR, "open_hours_local": INT_LIST}),
    "atr": {"period": POS_INT},
    "swings": {"strength": ("tfmap", POS_INT), "history": POS_INT},
    "zones": {
        "timeframes": TF_LIST,
        "base_max_candles": POS_INT,
        "base_max_range_atr": POS_NUM,
        "departure_max_candles": POS_INT,
        "departure_min_body_atr": POS_NUM,
        "departure_min_move_atr": POS_NUM,
        "break_close_buffer_atr": NUM,
        "max_age_bars": POS_INT,
        "max_tests": POS_INT,
        "merge_overlap_ratio": POS_NUM,
    },
    "scoring": {
        "top_n": POS_INT,
        "weights": {
            "freshness": NUM, "departure": NUM, "base": NUM, "volume": NUM,
            "room": NUM, "nesting": NUM, "liquidity": NUM, "timeframe": NUM,
        },
        "timeframe_weight": ("tfmap", NUM),
        "departure_cap_atr": POS_NUM,
        "volume_cap_ratio": POS_NUM,
        "volume_lookback": POS_INT,
        "room_cap_atr": POS_NUM,
        "liquidity_proximity_atr": POS_NUM,
    },
    "displacement": {"timeframes": TF_LIST, "min_body_atr": POS_NUM, "min_body_ratio": POS_NUM},
    "trend": {"timeframes": TF_LIST, "break_buffer_atr": NUM, "history": POS_INT},
    "fvg": {"timeframes": TF_LIST, "min_gap_atr": POS_NUM, "max_age_bars": POS_INT},
    "order_blocks": {
        "timeframes": TF_LIST, "lookback_bars": POS_INT, "require_displacement": BOOL,
        "break_buffer_atr": NUM, "max_age_bars": POS_INT, "max_tests": POS_INT,
    },
    "liquidity": {
        "detect_timeframe": TF, "swing_timeframes": TF_LIST, "equal_timeframes": TF_LIST,
        "equal_tolerance_atr": POS_NUM, "equal_lookback_swings": POS_INT,
        "min_pierce_atr": NUM, "break_buffer_atr": NUM, "reclaim_buffer_atr": NUM,
        "false_break_bars": POS_INT, "max_age_hours": POS_INT,
    },
    "ranges": {
        "timeframes": TF_LIST, "window_bars": POS_INT, "max_width_atr": POS_NUM,
        "touch_tolerance_atr": POS_NUM, "min_touches": POS_INT, "break_buffer_atr": NUM,
        "max_bars": POS_INT,
    },
    "htf_levels": {
        "swing_timeframes": TF_LIST, "session_levels": BOOL, "atr_timeframe": TF,
        "merge_tolerance_atr": POS_NUM, "touch_tolerance_atr": POS_NUM, "reset_atr": POS_NUM,
        "hold_atr": POS_NUM, "break_timeframe": TF, "break_buffer_atr": NUM, "max_age_hours": POS_INT,
        "approach_bars": POS_INT,
        "push": {"min_move_atr": POS_NUM, "min_efficiency": POS_NUM},
        "squeeze": {"min_pressing_bars": POS_INT, "max_range_ratio": POS_NUM, "min_drift_atr": NUM},
        "stretch_lookback_hours": POS_INT,
        "rejection_within_bars": POS_INT, "rejection_min_pierce_atr": NUM,
        "followthrough_bars": POS_INT, "followthrough_atr": POS_NUM,
        "pattern_link_atr": POS_NUM, "pattern_link_hours": POS_INT,
    },
    "vwap": {
        "anchors": ("list", STR),
        "day_anchor": {"timezone": STR, "hour": INT},
        "bands": ("list", POS_NUM),
        "detect_timeframe": TF, "cross_buffer_atr": NUM,
        "reject_band": POS_NUM,
        "min_bars": POS_INT,
    },
    "sessions": {
        "week_anchor": {"timezone": STR, "weekday": INT, "hour": INT},
        "day_start_utc_hour": INT,
        "windows_utc": ("map", ("pair", INT)),
        "history": POS_INT,
    },
    "close_spikes": {
        "timeframes": TF_LIST,
        "window_minutes": POS_INT,
        "atr_timeframe": TF,
        "min_move_atr": POS_NUM,
        "min_move_price": NUM,
        "held_close_fraction": POS_NUM,
        "horizons_minutes": INT_LIST,
        "reversal_retrace": POS_NUM,
        "volume_lookback": POS_INT,
        "level_lookback_hours": POS_INT,
    },
    "patterns": {
        "atr_timeframe": TF,
        "peak_tolerance_atr": POS_NUM,
        "min_neckline_depth_atr": POS_NUM,
        "prior_move_min_atr": POS_NUM,
        "prior_move_lookback_bars": POS_INT,
        "min_depth_prior_move_ratio": POS_NUM,
        "triple_trough_tolerance_atr": POS_NUM,
        "min_bars_between_peaks": POS_INT,
        "max_bars_between_peaks": POS_INT,
        "confirm_within_bars": POS_INT,
        "invalidate_beyond_atr": NUM,
        "sweep_min_atr": NUM,
        "volume_spike_ratio": POS_NUM,
        "volume_lookback": POS_INT,
        "exhaustion_wick_ratio": POS_NUM,
        "history": POS_INT,
    },
}


class ConfigError(ValueError):
    """Raised for any unknown, missing or ill-typed config value."""


class StructureConfig(dict):
    """The validated config: a plain dict plus ``config_hash`` and helpers.

    It stays a dict on purpose: detectors read ``cfg["zones"]["max_tests"]``
    directly, so grepping a key name finds every place that uses it.
    """

    config_hash: str
    tf_minutes: dict[str, int]

    def minutes(self, tf: str) -> int:
        return self.tf_minutes[tf]


def _check(value: Any, schema: Any, path: str, tfs: set[str]) -> None:
    """Recursively validate ``value`` against ``schema``; raise ConfigError."""
    if isinstance(schema, dict):
        if not isinstance(value, dict):
            raise ConfigError(f"{path}: expected an object")
        unknown = sorted(set(value) - set(schema))
        missing = sorted(set(schema) - set(value))
        if unknown:
            raise ConfigError(f"{path}: unknown key(s) {unknown}")
        if missing:
            raise ConfigError(f"{path}: missing key(s) {missing}")
        for key, sub in schema.items():
            _check(value[key], sub, f"{path}.{key}", tfs)
        return
    if isinstance(schema, tuple):
        kind, leaf = schema
        if kind in ("map", "tfmap"):
            if not isinstance(value, dict) or not value:
                raise ConfigError(f"{path}: expected a non-empty object")
            for key, item in value.items():
                if kind == "tfmap" and key not in tfs:
                    raise ConfigError(f"{path}: '{key}' is not a declared timeframe")
                _check(item, leaf, f"{path}.{key}", tfs)
            return
        if kind == "list":
            if not isinstance(value, list) or not value:
                raise ConfigError(f"{path}: expected a non-empty list")
            for i, item in enumerate(value):
                _check(item, leaf, f"{path}[{i}]", tfs)
            return
        if kind == "pair":
            if not isinstance(value, list) or len(value) != 2:
                raise ConfigError(f"{path}: expected a two-element list")
            for i, item in enumerate(value):
                _check(item, leaf, f"{path}[{i}]", tfs)
            return
        raise AssertionError(kind)
    # Leaves. bool is a subclass of int in Python, so it is excluded explicitly.
    is_int = isinstance(value, int) and not isinstance(value, bool)
    is_num = is_int or isinstance(value, float)
    ok = {
        INT: is_int, POS_INT: is_int and value > 0,
        NUM: is_num, POS_NUM: is_num and value > 0,
        STR: isinstance(value, str) and bool(value),
        TF: isinstance(value, str) and value in tfs,
        BOOL: isinstance(value, bool),
        INT_LIST: isinstance(value, list) and bool(value) and all(
            isinstance(v, int) and not isinstance(v, bool) for v in value),
        TF_LIST: isinstance(value, list) and bool(value) and all(v in tfs for v in value),
    }[schema]
    if not ok:
        raise ConfigError(f"{path}: invalid value {value!r} (expected {schema})")


def config_hash(raw: dict) -> str:
    """Stable fingerprint: sha256 of canonical JSON (sorted keys, no spaces)."""
    canonical = json.dumps(raw, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()[:16]


def load_config(path: str | Path | None = None, overrides: dict | None = None) -> StructureConfig:
    """Load, validate and fingerprint a structure config.

    ``overrides`` (nested dict) is merged on top before validation — used by
    tests and parameter sweeps. Overridden configs get their own hash.
    """
    path = Path(path) if path else DEFAULT_CONFIG
    raw = json.loads(path.read_text(encoding="utf-8"))
    if overrides:
        raw = _deep_merge(raw, overrides)
    return build_config(raw)


def build_config(raw: dict) -> StructureConfig:
    """Validate an in-memory config dict (see load_config)."""
    if not isinstance(raw, dict) or "timeframes" not in raw:
        raise ConfigError("config must be an object with 'timeframes'")
    tfs = set(raw["timeframes"]) if isinstance(raw["timeframes"], dict) else set()
    _check(raw, SCHEMA, "config", tfs)
    if raw["timeframes"].get("M1") != 1:
        raise ConfigError("config.timeframes must declare M1 = 1 (the input bar size)")
    for tf, minutes in raw["timeframes"].items():
        if 1440 % minutes != 0:
            raise ConfigError(f"timeframe {tf}={minutes} must divide a day evenly")
    from .clock import TIMEZONES
    for tf, rule in raw["alignment"].items():
        src, minutes = rule["source"], raw["timeframes"][tf]
        if tf == "M1" or raw["timeframes"][src] >= minutes or minutes % raw["timeframes"][src]:
            raise ConfigError(f"alignment.{tf}: source {src} must be a smaller timeframe that divides it")
        if src in raw["alignment"]:
            raise ConfigError(f"alignment.{tf}: source {src} may not itself be anchored")
        if rule["timezone"] not in TIMEZONES:
            raise ConfigError(f"alignment.{tf}: timezone must be one of {sorted(TIMEZONES)}")
        hours = sorted(rule["open_hours_local"])
        step = minutes // 60
        if minutes % 60 or len(hours) * minutes != 1440 or any(
                b - a != step for a, b in zip(hours, hours[1:])) or not all(0 <= h < 24 for h in hours):
            raise ConfigError(f"alignment.{tf}: open_hours_local must be every {step}h covering the day")
    if set(raw["swings"]["strength"]) != tfs:
        raise ConfigError("swings.strength must list every declared timeframe")
    if set(raw["scoring"]["timeframe_weight"]) != set(raw["zones"]["timeframes"]):
        raise ConfigError("scoring.timeframe_weight must cover exactly zones.timeframes")
    for name, (start, end) in raw["sessions"]["windows_utc"].items():
        if not (0 <= start < end <= 24):
            raise ConfigError(f"sessions.windows_utc.{name} must satisfy 0 <= start < end <= 24")
    if not set(raw["order_blocks"]["timeframes"]) <= set(raw["trend"]["timeframes"]):
        raise ConfigError("order_blocks.timeframes must be a subset of trend.timeframes")
    if not set(raw["order_blocks"]["timeframes"]) <= set(raw["displacement"]["timeframes"]):
        raise ConfigError("order_blocks.timeframes must be a subset of displacement.timeframes")
    wa = raw["sessions"]["week_anchor"]
    if wa["timezone"] not in TIMEZONES or not 0 <= wa["weekday"] <= 6 or not 0 <= wa["hour"] <= 23:
        raise ConfigError("sessions.week_anchor: timezone, weekday 0-6 (Monday=0), hour 0-23")
    vw = raw["vwap"]
    if not set(vw["anchors"]) <= {"day", "week", "session"} or len(set(vw["anchors"])) != len(vw["anchors"]):
        raise ConfigError("vwap.anchors: unique values from day, week, session")
    if vw["day_anchor"]["timezone"] not in TIMEZONES or not 0 <= vw["day_anchor"]["hour"] <= 23:
        raise ConfigError("vwap.day_anchor: known timezone and hour 0-23")
    if vw["reject_band"] not in vw["bands"]:
        raise ConfigError("vwap.reject_band must be one of vwap.bands")
    hl = raw["htf_levels"]
    if not hl["touch_tolerance_atr"] < hl["reset_atr"]:
        raise ConfigError("htf_levels: touch_tolerance_atr must be smaller than reset_atr")
    if hl["followthrough_atr"] > hl["hold_atr"]:
        raise ConfigError("htf_levels: followthrough_atr must not exceed hold_atr")
    cs = raw["close_spikes"]
    if any(h <= 0 for h in cs["horizons_minutes"]):
        raise ConfigError("close_spikes.horizons_minutes must be positive")
    if any(raw["timeframes"][tf] <= cs["window_minutes"] for tf in cs["timeframes"]):
        raise ConfigError("close_spikes.window_minutes must be shorter than every spike timeframe")
    p = raw["patterns"]
    if p["min_bars_between_peaks"] >= p["max_bars_between_peaks"]:
        raise ConfigError("patterns: min_bars_between_peaks must be < max_bars_between_peaks")

    cfg = StructureConfig(json.loads(json.dumps(raw)))  # deep copy, JSON types only
    cfg.config_hash = config_hash(raw)
    cfg.tf_minutes = dict(raw["timeframes"])
    return cfg


def _deep_merge(base: dict, extra: dict) -> dict:
    out = json.loads(json.dumps(base))
    for key, value in extra.items():
        if isinstance(value, dict) and isinstance(out.get(key), dict):
            out[key] = _deep_merge(out[key], value)
        else:
            out[key] = value
    return out
