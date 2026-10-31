"""Strict config for the research lab (same rules as the structure engine:
unknown / missing / ill-typed keys fail; the whole config is hashed)."""

from __future__ import annotations

import json
from pathlib import Path

from structure_engine.config import (BOOL, NUM, POS_INT, POS_NUM, STR, ConfigError, _check,
                                     config_hash)

DEFAULT = Path(__file__).resolve().parent / "config" / "lab_v1.json"
TFS = {"M1", "M5", "M15", "M30", "H1", "H4"}
TF_LIST_FREE = "tf_list"

SCHEMA = {
    "lab_id": STR,
    "decision_timeframe": STR,
    "barrier_atr": POS_NUM,
    "label_tolerance_minutes": POS_INT,
    "forecast": {
        "timeframes": ("map", {"lookback": POS_INT, "horizon": POS_INT}),
        "paths": POS_INT,
        "temperature": POS_NUM,
        "top_p": POS_NUM,
        "seed": POS_INT,
        "kronos_model": STR,
        "kronos_tokenizer": STR,
        "max_context": POS_INT,
    },
    "walk_forward": {"initial_train_fraction": POS_NUM, "retrain_every": POS_INT, "min_train": POS_INT},
    "xgboost": {"n_estimators": POS_INT, "max_depth": POS_INT, "learning_rate": POS_NUM,
                "subsample": POS_NUM, "colsample_bytree": POS_NUM, "min_child_weight": POS_NUM,
                "reg_lambda": NUM, "use_xgboost": BOOL},
}


def load_lab_config(path: str | Path | None = None) -> dict:
    raw = json.loads(Path(path or DEFAULT).read_text(encoding="utf-8"))
    _check(raw, SCHEMA, "lab", TFS)
    if raw["decision_timeframe"] not in TFS:
        raise ConfigError("decision_timeframe must be one of " + ", ".join(sorted(TFS)))
    for tf in raw["forecast"]["timeframes"]:
        if tf not in TFS:
            raise ConfigError(f"forecast.timeframes: unknown timeframe {tf}")
    if not 0 < raw["walk_forward"]["initial_train_fraction"] < 1:
        raise ConfigError("walk_forward.initial_train_fraction must be between 0 and 1")
    raw["_hash"] = config_hash({k: v for k, v in raw.items() if k != "_hash"})
    return raw
