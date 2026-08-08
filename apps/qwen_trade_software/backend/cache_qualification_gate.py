"""Cache qualification gate used before the trading chain may start."""

from __future__ import annotations

import json
import logging
import subprocess
import time
from pathlib import Path

from market_context_cache import DEFAULT_DB, latest_readiness


APP_DIR = Path(__file__).resolve().parent
PYTHON = Path(r"C:\ProgramData\Miniconda3\python.exe")
DEFAULT_SYMBOL = "XAUUSDr"
QUALIFICATION_TIMEOUT_SECONDS = 900


def cache_manifest(symbol: str = DEFAULT_SYMBOL, db: Path | str = DEFAULT_DB) -> dict | None:
    return latest_readiness(symbol, db)


def cache_is_ready(manifest: dict | None) -> bool:
    if not manifest:
        return False
    return (
        manifest.get("status") == "ready"
        and manifest.get("context_challenge_valid") is True
    )


def parse_manifest_output(output: str) -> dict | None:
    """Return the last JSON object printed by market_context_cache --once."""
    text = output.strip()
    if not text:
        return None
    decoder = json.JSONDecoder()
    manifest = None
    index = 0
    while index < len(text):
        while index < len(text) and text[index].isspace():
            index += 1
        if index >= len(text):
            break
        try:
            manifest, offset = decoder.raw_decode(text, index)
            index += offset
        except json.JSONDecodeError:
            break
    return manifest if isinstance(manifest, dict) else None


def run_qualification_once(
    symbol: str = DEFAULT_SYMBOL,
    *,
    python: Path = PYTHON,
    app_dir: Path = APP_DIR,
) -> dict:
    command = [
        str(python),
        str(app_dir / "market_context_cache.py"),
        "--once",
        "--no-minute-benchmark",
        "--symbol",
        symbol,
    ]
    started = time.perf_counter()
    completed = subprocess.run(
        command,
        cwd=app_dir,
        capture_output=True,
        text=True,
        timeout=QUALIFICATION_TIMEOUT_SECONDS,
        check=False,
    )
    wall_seconds = round(time.perf_counter() - started, 2)
    manifest = parse_manifest_output(completed.stdout)
    if manifest is None:
        manifest = {
            "status": "blocked",
            "failures": ["qualification_process_failed"],
            "process_exit_code": completed.returncode,
            "stderr_tail": completed.stderr[-500:],
        }
    manifest["qualification_wall_seconds"] = wall_seconds
    manifest["qualification_exit_code"] = completed.returncode
    if completed.returncode != 0 and cache_is_ready(manifest):
        logging.warning(
            "Qualification process exited %s but manifest is ready",
            completed.returncode,
        )
    if not cache_is_ready(manifest):
        logging.error(
            "Cache qualification failed in %.2fs failures=%s stderr=%s",
            wall_seconds,
            manifest.get("failures"),
            completed.stderr[-300:],
        )
    else:
        logging.info("Cache qualification succeeded in %.2fs", wall_seconds)
    return manifest


def ensure_cache_ready(
    symbol: str = DEFAULT_SYMBOL,
    *,
    retry_seconds: int = 10,
    stop_callback=None,
) -> dict:
    """Block until cache qualification is ready or stop_callback returns True."""
    while True:
        if stop_callback and stop_callback():
            raise RuntimeError("Cache qualification interrupted")
        manifest = cache_manifest(symbol)
        if cache_is_ready(manifest):
            logging.info("Cache qualification gate open for %s", symbol)
            return manifest
        failures = (manifest or {}).get("failures", ["readiness_missing"])
        logging.warning(
            "Cache qualification required before trading (failures=%s); running qualification",
            failures,
        )
        manifest = run_qualification_once(symbol)
        if cache_is_ready(manifest):
            return manifest
        logging.error(
            "Cache qualification still blocked; retrying in %ss failures=%s",
            retry_seconds,
            manifest.get("failures"),
        )
        deadline = time.monotonic() + retry_seconds
        while time.monotonic() < deadline:
            if stop_callback and stop_callback():
                raise RuntimeError("Cache qualification interrupted")
            time.sleep(1)


if __name__ == "__main__":
    import sys

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(message)s",
    )
    try:
        result = ensure_cache_ready()
        print(json.dumps(result, indent=2))
        sys.exit(0 if cache_is_ready(result) else 1)
    except RuntimeError as error:
        print(str(error), file=sys.stderr)
        sys.exit(1)
