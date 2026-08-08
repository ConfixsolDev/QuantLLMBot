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


class QwenTradeSoftware:
    """Start and supervise every component required by the local application."""

    APP_DIR = Path(__file__).resolve().parent
    LOG_DIR = APP_DIR / "logs"
    RUNTIME_LOG = LOG_DIR / "software-runtime.log"
    LOCK_FILE = APP_DIR / "software-runtime.lock"

    PYTHON = Path(r"C:\ProgramData\Miniconda3\python.exe")
    MT5 = Path(r"C:\Program Files\MetaTrader 5\terminal64.exe")
    OLLAMA_APP = Path(os.environ.get("LOCALAPPDATA", "")) / "Programs" / "Ollama" / "ollama app.exe"

    OLLAMA_HEALTH = "http://127.0.0.1:11434/api/tags"
    DASHBOARD_HEALTH = "http://127.0.0.1:48632/snapshot"
    WEBSITE_HEALTH = "http://127.0.0.1:8080/"

    def __init__(self) -> None:
        self.LOG_DIR.mkdir(parents=True, exist_ok=True)
        logging.basicConfig(
            filename=self.RUNTIME_LOG,
            level=logging.INFO,
            format="%(asctime)s %(levelname)s %(message)s",
        )
        self.children: dict[str, subprocess.Popen] = {}
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
        self.lock_handle.flush()

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
        for url in (self.WEBSITE_HEALTH, "http://127.0.0.1/"):
            if self._http_ok(url):
                self.WEBSITE_HEALTH = url
                return
        subprocess.run(
            ["sc.exe", "start", "W3SVC"],
            capture_output=True,
            creationflags=self._hidden_flags(),
            check=False,
        )
        if not self._wait_for(self.WEBSITE_HEALTH, 30) and not self._wait_for(
            "http://127.0.0.1/", 15
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
        logging.info("Started %s pid=%s", name, self.children[name].pid)

    @staticmethod
    def _child_command(name: str) -> tuple[str, ...]:
        commands = {
            "reviewer": ("reviewer.py",),
            # 2026-08-06 split: trade management (the ongoing in-trade review
            # loop) moved out of reviewer.py into its own process -- it needs
            # its own knowledge base / skill path over time, separate from
            # entry-decision. See trade_management.py's module docstring.
            "trade_management": ("trade_management.py",),
            # Heavy Qwen qualification is manual/off-hours while the challenger
            # is blocked.  The always-on child keeps deterministic cache state
            # current without holding the model lock ahead of the champion.
            "context_cache": (
                "market_context_cache.py",
                "--no-qwen",
                "--no-minute-benchmark",
            ),
            "paper_runner": ("paper_runner.py",),
            "session_planner": ("session_planner.py",),
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
        # Load Qwen into Ollama memory before the --no-qwen cache worker runs.
        # Otherwise the first cache tick marks model_resident=false and blocks entry.
        warm = subprocess.run(
            [str(self.PYTHON), "-c", "from review_shared import warm_model; warm_model()"],
            cwd=self.APP_DIR,
            capture_output=True,
            text=True,
            timeout=120,
            creationflags=self._hidden_flags(),
            check=False,
        )
        if warm.returncode != 0:
            logging.warning("Model warm-up failed: %s", warm.stderr[-300:])
        else:
            logging.info("Qwen model warmed before cache worker start")
        self._start_child("trade_management", "trade_management.py")
        self._start_child(
            "context_cache",
            "market_context_cache.py",
            "--no-qwen",
            "--no-minute-benchmark",
        )
        self._start_child("paper_runner", "paper_runner.py")
        self._start_child("session_planner", "session_planner.py")
        logging.info("Complete software chain is ready")

    def run_forever(self) -> None:
        self.start()
        while not self.stopping:
            for name, process in tuple(self.children.items()):
                if process.poll() is not None:
                    logging.error("%s exited with code %s; restarting", name, process.returncode)
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
