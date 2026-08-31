"""Periodic broker-truth repair for missing paper execution closes.

This is deliberately deterministic and read/repair-only: MT5 history is the
source of truth, and no entry, exit, or strategy decision is changed.
"""
from __future__ import annotations

import argparse
import logging
import time
import subprocess
import sys
from pathlib import Path

APP_DIR = Path(__file__).resolve().parent
LOG_DIR = APP_DIR / "logs"


def reconcile_once(days: int = 7) -> int:
    tool = APP_DIR / "tools" / "reconcile_broker_truth.py"
    result = None
    for attempt in range(3):
        result = subprocess.run(
            [sys.executable, str(tool), "--days", str(max(1, int(days))), "--repair"],
            cwd=APP_DIR, capture_output=True, text=True, timeout=45, check=False,
        )
        output = (result.stderr or result.stdout).lower()
        if result.returncode == 0 or "database is locked" not in output:
            break
        time.sleep(1.0 * (attempt + 1))
    output_text = (result.stderr or result.stdout)
    if "MT5 unavailable" in output_text or "IPC send failed" in output_text:
        logging.warning("broker reconciliation deferred: %s", output_text[-300:].strip())
        return 0
    if result.returncode:
        logging.error("broker reconciliation failed rc=%s: %s", result.returncode,
                      output_text[-500:])
    elif "Wrote " in result.stdout:
        logging.info("broker reconciliation: %s", result.stdout.strip().splitlines()[-1])
    return result.returncode


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--interval", type=float, default=60.0)
    parser.add_argument("--days", type=int, default=7)
    args = parser.parse_args()
    LOG_DIR.mkdir(parents=True, exist_ok=True)
    logging.basicConfig(level=logging.INFO,
                        format="%(asctime)s %(levelname)s %(message)s",
                        handlers=[logging.FileHandler(LOG_DIR / "broker-reconciliation.log", encoding="utf-8"),
                                  logging.StreamHandler()])
    while True:
        reconcile_once(args.days)
        time.sleep(max(10.0, args.interval))


if __name__ == "__main__":
    raise SystemExit(main())
