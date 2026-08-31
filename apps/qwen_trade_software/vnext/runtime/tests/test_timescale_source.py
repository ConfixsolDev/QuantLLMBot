from datetime import datetime, timezone

from vnext.runtime.live_cycle import TimescaleClosedBarSource


class Cursor:
    def __init__(self): self.query = None
    def __enter__(self): return self
    def __exit__(self, *args): pass
    def execute(self, query, params): self.query = (query, params)
    def fetchall(self): return [(datetime(2026, 1, 1, tzinfo=timezone.utc), 1, 2, .5, 1.5, 3, 0)]


class Connection:
    def __enter__(self): return self
    def __exit__(self, *args): pass
    def cursor(self): return Cursor()


def test_timescale_source_uses_only_completed_m1_rows(monkeypatch):
    import psycopg
    monkeypatch.setattr(psycopg, "connect", lambda *args, **kwargs: Connection())
    rows = list(TimescaleClosedBarSource("dsn").closed_m1("XAUUSD", 10))
    assert rows[0]["close"] == 1.5
