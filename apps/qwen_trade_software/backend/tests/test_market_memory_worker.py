import os

import market_memory_worker


def test_health_publication_retries_windows_reader_lock(tmp_path, monkeypatch):
    target = tmp_path / "health.json"
    real_replace = os.replace
    calls = {"count": 0}

    def flaky_replace(source, destination):
        calls["count"] += 1
        if calls["count"] < 3:
            raise PermissionError("simulated Windows reader lock")
        return real_replace(source, destination)

    monkeypatch.setattr(market_memory_worker.os, "replace", flaky_replace)
    assert market_memory_worker.write_health(
        {"status": "ready"}, target=target, attempts=3, retry_seconds=0
    )
    assert calls["count"] == 3
    assert target.read_text(encoding="utf-8") == '{"status": "ready"}'


def test_health_failure_is_nonfatal_and_cleans_temporary_file(tmp_path, monkeypatch):
    target = tmp_path / "health.json"

    def locked_replace(source, destination):
        raise PermissionError("simulated persistent reader lock")

    monkeypatch.setattr(market_memory_worker.os, "replace", locked_replace)
    assert not market_memory_worker.write_health(
        {"status": "ready"}, target=target, attempts=2, retry_seconds=0
    )
    assert list(tmp_path.glob("*.tmp")) == []
