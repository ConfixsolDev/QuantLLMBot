"""Single entry point for the complete local GoldFlow/Qwen software."""

from __future__ import annotations

import atexit
import json
import logging
import msvcrt
import os
import signal
import subprocess
import sys
import time
import urllib.request
from pathlib import Path

import process_logging


class QwenTradeSoftware:
    """Start and supervise every component required by the local application."""

    APP_DIR = Path(__file__).resolve().parent
    LOG_DIR = APP_DIR / "logs"
    RUNTIME_LOG = LOG_DIR / "software-runtime.log"
    LOCK_FILE = APP_DIR / "software-runtime.lock"

    _LOCAL_PYTHON = APP_DIR / ".venv" / "Scripts" / "python.exe"
    PYTHON = (
        _LOCAL_PYTHON
        if _LOCAL_PYTHON.exists()
        else Path(r"C:\ProgramData\Miniconda3\python.exe")
    )
    MT5 = Path(r"C:\Program Files\MetaTrader 5\terminal64.exe")
    OLLAMA_APP = Path(os.environ.get("LOCALAPPDATA", "")) / "Programs" / "Ollama" / "ollama app.exe"

    OLLAMA_HEALTH = "http://127.0.0.1:11434/api/tags"
    DASHBOARD_HEALTH = "http://127.0.0.1:48632/snapshot"
    # GoldFlow Plan View (sole UI). Prefer :8088; :80 is also bound after deploy.
    WEBSITE_HEALTH = "http://127.0.0.1:8088/"

    def __init__(self) -> None:
        self.LOG_DIR.mkdir(parents=True, exist_ok=True)
        process_logging.configure(self.RUNTIME_LOG, owner="software_runtime")
        self.children: dict[str, subprocess.Popen] = {}
        self.child_started_at: dict[str, float] = {}
        self.child_restarts: dict[str, int] = {}
        self.stopping = False
        self.lock_handle = None

    @staticmethod
    def _hidden_flags() -> int:
        return getattr(subprocess, "CREATE_NO_WINDOW", 0)

    @staticmethod
    def _http_ok(url: str, timeout: float = 3.0) -> bool:
        try:
            with urllib.request.urlopen(url, timeout=timeout) as response:
                return 200 <= response.status < 300
        except Exception:
            return False

    @staticmethod
    def _process_running(image_name: str) -> bool:
        result = subprocess.run(
            ["tasklist.exe", "/FI", f"IMAGENAME eq {image_name}", "/FO", "CSV", "/NH"],
            capture_output=True,
            text=True,
            creationflags=QwenTradeSoftware._hidden_flags(),
            check=False,
        )
        return image_name.lower() in result.stdout.lower()

    def _acquire_singleton(self) -> None:
        self.lock_handle = self.LOCK_FILE.open("a+")
        try:
            msvcrt.locking(self.lock_handle.fileno(), msvcrt.LK_NBLCK, 1)
        except OSError as error:
            raise RuntimeError("QwenTradeSoftware is already running") from error
        self.lock_handle.seek(0)
        self.lock_handle.truncate()
        self.lock_handle.write(
            json.dumps({"pid": os.getpid(), "started_at": time.time()})
        )
        try:
            self.lock_handle.flush()
        except PermissionError:
            # Byte-range lock is already held; an empty/partial lock file is
            # worse for diagnostics than for safety. Do not abort the chain.
            logging.warning("Could not flush software-runtime.lock; continuing with lock held")

    def _launch_desktop_dependencies(self) -> None:
        if not self._process_running("terminal64.exe"):
            subprocess.Popen(
                [str(self.MT5)],
                cwd=self.MT5.parent,
                creationflags=self._hidden_flags(),
            )
            logging.info("Started MetaTrader 5")

        if not self._http_ok(self.OLLAMA_HEALTH, timeout=2):
            subprocess.Popen(
                [str(self.OLLAMA_APP)],
                cwd=self.OLLAMA_APP.parent,
                creationflags=self._hidden_flags(),
            )
            logging.info("Started Ollama Windows app")

    def _ensure_website(self) -> None:
        for url in (self.WEBSITE_HEALTH, "http://127.0.0.1/", "http://127.0.0.1:8080/"):
            if self._http_ok(url):
                self.WEBSITE_HEALTH = url
                return
        subprocess.run(
            ["sc.exe", "start", "W3SVC"],
            capture_output=True,
            creationflags=self._hidden_flags(),
            check=False,
        )
        if (
            not self._wait_for(self.WEBSITE_HEALTH, 30)
            and not self._wait_for("http://127.0.0.1/", 15)
        ):
            logging.warning("Website health check failed; continuing without IIS")

    def _start_child(self, name: str, script: str, *extra_args: str) -> None:
        self.children[name] = subprocess.Popen(
            [str(self.PYTHON), str(self.APP_DIR / script), *extra_args],
            cwd=self.APP_DIR,
            stdin=subprocess.DEVNULL,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            creationflags=self._hidden_flags(),
        )
        self.child_started_at[name] = time.monotonic()
        logging.info("Started %s pid=%s", name, self.children[name].pid)
        process_logging.structured_event(
            "child_started",
            child=name,
            pid=self.children[name].pid,
            script=script,
            restart_count=self.child_restarts.get(name, 0),
        )

    @staticmethod
    def _child_command(name: str) -> tuple[str, ...]:
        commands = {
            "reviewer": ("reviewer.py",),
            # 2026-08-06 split: trade management (the ongoing in-trade review
            # loop) moved out of reviewer.py into its own process -- it needs
            # its own knowledge base / skill path over time, separate from
            # entry-decision. See trade_management.py's module docstring.
            "trade_management": ("trade_management.py",),
            "profit_protection": ("profit_protection.py",),
            # Steady-state cache ticks skip Qwen (--no-qwen) so they do not
            # hold the model lock. market_context_cache overrides that for one
            # cycle when the qualification certificate is missing or bound to
            # another model digest.
            "context_cache": (
                "market_context_cache.py",
                "--no-qwen",
                "--no-minute-benchmark",
                "--interval",
                "30",
            ),
            "market_memory": ("market_memory_worker.py", "--interval", "2"),
            "trade_journal": ("trade_journal_worker.py", "--interval", "15"),
            "broker_reconciliation": ("broker_reconciliation_worker.py", "--interval", "60"),
            "market_graph": ("market_graph_worker.py",),
            "paper_runner": ("paper_runner.py",),
            "session_planner": ("session_planner.py",),
            "intraday_observer": ("intraday_observer_worker.py",),
        }
        return commands[name]

    def _wait_for(self, url: str, seconds: int) -> bool:
        deadline = time.monotonic() + seconds
        while time.monotonic() < deadline and not self.stopping:
            if self._http_ok(url):
                return True
            time.sleep(2)
        return False

    def start(self) -> None:
        self._acquire_singleton()
        logging.info("Runtime Python: %s", self.PYTHON)
        from storage_config import StorageConfig
        storage_health = StorageConfig.from_env().validate_activation()
        logging.info("Storage activation health: %s", storage_health)
        # Live Timescale mode owns runtime history.  The legacy JSONL archive
        # synchronizer is retained for offline/replay mode only.
        if os.environ.get("QWEN_INTELLIGENCE_BACKEND", "sqlite").strip().lower() != "timescale":
            from tick_data_archive import sync_all_archives, write_all_day_manifests, write_day_manifest
            synced = sync_all_archives()
            if synced:
                logging.info("Synced tick data archive: %d file(s)", len(synced))
            write_day_manifest()
            manifests = write_all_day_manifests()
            if manifests:
                logging.info("Refreshed %d tick_data day manifest(s)", manifests)
        self._launch_desktop_dependencies()
        if not self._wait_for(self.OLLAMA_HEALTH, 90):
            raise RuntimeError("Ollama/Qwen did not become ready")
        self._ensure_website()
        self._start_child("reviewer", "reviewer.py")
        if not self._wait_for(self.DASHBOARD_HEALTH, 30):
            raise RuntimeError("Reviewer dashboard API did not become ready")
        # Load Qwen only when gold is quoting; unload when the market is closed.
        # Otherwise a weekend/off-hours start leaves the model pinned for nothing,
        # and a closed-market first cache tick can mark model_resident=false.
        warm = subprocess.run(
            [
                str(self.PYTHON),
                "-c",
                "from review_shared import sync_model_residency; "
                "print(sync_model_residency())",
            ],
            cwd=self.APP_DIR,
            capture_output=True,
            text=True,
            timeout=120,
            creationflags=self._hidden_flags(),
            check=False,
        )
        if warm.returncode != 0:
            logging.warning("Model residency sync failed: %s", warm.stderr[-300:])
        else:
            logging.info("Model residency sync: %s", (warm.stdout or "").strip()[-300:])
        self._start_child("trade_management", "trade_management.py")
        self._start_child("profit_protection", "profit_protection.py")
        self._start_child(
            "context_cache",
            "market_context_cache.py",
            "--no-qwen",
            "--no-minute-benchmark",
            "--interval",
            "30",
        )
        self._start_child("market_memory", "market_memory_worker.py", "--interval", "2")
        self._start_child("trade_journal", "trade_journal_worker.py", "--interval", "15")
        self._start_child("broker_reconciliation", "broker_reconciliation_worker.py", "--interval", "60")
        from runtime_config import NEO4J_ENABLED
        if NEO4J_ENABLED:
            self._start_child("market_graph", "market_graph_worker.py")
        self._start_child("paper_runner", "paper_runner.py")
        self._start_child("session_planner", "session_planner.py")
        self._start_child("intraday_observer", "intraday_observer_worker.py")
        logging.info("Complete software chain is ready")

    def run_forever(self) -> None:
        self.start()
        while not self.stopping:
            for name, process in tuple(self.children.items()):
                if process.poll() is not None:
                    logging.error("%s exited with code %s; restarting", name, process.returncode)
                    uptime = time.monotonic() - self.child_started_at.get(name, time.monotonic())
                    self.child_restarts[name] = self.child_restarts.get(name, 0) + 1
                    process_logging.structured_event(
                        "child_exited",
                        level=logging.ERROR,
                        child=name,
                        pid=process.pid,
                        return_code=process.returncode,
                        uptime_seconds=round(uptime, 2),
                        restart_count=self.child_restarts[name],
                    )
                    self._start_child(name, *self._child_command(name))
            if not self._http_ok(self.OLLAMA_HEALTH):
                logging.error("Ollama health check failed")
            if not self._http_ok(self.WEBSITE_HEALTH):
                logging.error("Website health check failed")
            time.sleep(5)

    def stop(self) -> None:
        if self.stopping:
            return
        self.stopping = True
        for name, process in reversed(tuple(self.children.items())):
            if process.poll() is None:
                process.terminate()
                try:
                    process.wait(timeout=10)
                except subprocess.TimeoutExpired:
                    process.kill()
                logging.info("Stopped %s", name)
        if self.lock_handle is not None:
            try:
                self.lock_handle.close()
            except Exception:
                pass


def main() -> None:
    software = QwenTradeSoftware()
    atexit.register(software.stop)
    signal.signal(signal.SIGTERM, lambda *_: software.stop())
    signal.signal(signal.SIGINT, lambda *_: software.stop())
    software.run_forever()


if __name__ == "__main__":
    try:
        main()
    except Exception:
        logging.exception("Unified software runtime stopped")
        raise
