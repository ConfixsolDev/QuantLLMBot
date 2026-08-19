"""Append-only, correlated observability trail for trade opportunities."""

import logging
from datetime import datetime, timezone

from tick_data_archive import append_tick_record


def log_step(stage: str, status: str, **fields) -> None:
    record = {
        "schema_version": 1,
        "timestamp_utc": datetime.now(timezone.utc).isoformat(),
        "stage": stage,
        "status": status,
        **{key: value for key, value in fields.items() if value is not None},
    }
    try:
        append_tick_record("trade-steps", record)
    except Exception:
        logging.exception("TRADE_STEP write failed stage=%s status=%s", stage, status)
    logging.info(
        "TRADE_STEP stage=%s status=%s proposal=%s execution=%s price=%s detail=%s",
        stage, status, fields.get("proposal_id"), fields.get("execution_id"),
        fields.get("price"), fields.get("detail"),
    )
