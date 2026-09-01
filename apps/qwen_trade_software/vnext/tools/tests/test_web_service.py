import json
import threading
import urllib.error
import urllib.request
from datetime import datetime, timezone
from http.server import ThreadingHTTPServer
from pathlib import Path

from vnext.tools.run_web_service import make_handler, merge_candles


class FakeReader:
    def snapshot(self):
        return {
            "schema_version": "VNEXT_WEB_STATUS_V2",
            "generated_at_utc": datetime.now(timezone.utc).isoformat(),
            "read_only": True,
            "architecture": "V2/vNext",
            "latest": {},
            "counts_24h": {},
            "recent_events": [],
        }


def _serve(tmp_path: Path):
    (tmp_path / "index.html").write_text("vNext dashboard", encoding="utf-8")
    (tmp_path / "styles.css").write_text("body{}", encoding="utf-8")
    (tmp_path / "app.js").write_text("", encoding="utf-8")
    server = ThreadingHTTPServer(("127.0.0.1", 0), make_handler(FakeReader(), tmp_path))
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    return server, thread


def test_web_status_is_vnext_and_read_only(tmp_path):
    server, thread = _serve(tmp_path)
    try:
        base = f"http://127.0.0.1:{server.server_port}"
        with urllib.request.urlopen(base + "/api/status") as response:
            payload = json.load(response)
        assert payload["architecture"] == "V2/vNext"
        assert payload["read_only"] is True
        request = urllib.request.Request(base + "/api/status", data=b"{}", method="POST")
        try:
            urllib.request.urlopen(request)
        except urllib.error.HTTPError as exc:
            assert exc.code == 405
        else:
            raise AssertionError("write request must be rejected")
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=2)


def test_web_root_serves_dashboard(tmp_path):
    server, thread = _serve(tmp_path)
    try:
        with urllib.request.urlopen(f"http://127.0.0.1:{server.server_port}/") as response:
            assert response.read() == b"vNext dashboard"
            assert "default-src 'self'" in response.headers["Content-Security-Policy"]
        for route in ("/operations", "/history", "/trades"):
            with urllib.request.urlopen(f"http://127.0.0.1:{server.server_port}{route}") as response:
                assert response.read() == b"vNext dashboard"
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=2)


def test_market_candles_merge_prefers_fresh_working_memory():
    durable = [{"timeframe": "M15", "open_time_utc": "2026-01-01T00:00:00+00:00",
                "close_time_utc": "2026-01-01T00:15:00+00:00", "open": 10,
                "high": 12, "low": 9, "close": 11, "tick_volume": 4, "spread": 2}]
    working = [{"timeframe": "M15", "start_utc": "2026-01-01T00:00:00+00:00",
                "end_utc": "2026-01-01T00:15:00+00:00", "open": 10,
                "high": 13, "low": 9, "close": 12, "tick_volume": 7, "spread": 2}]
    result = merge_candles(durable, working)
    assert len(result) == 1
    assert result[0]["close"] == 12
    assert result[0]["source"] == "working_memory"
