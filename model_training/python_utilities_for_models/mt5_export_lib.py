"""Shared MT5 historical export helpers for v003 dataset Layer 0."""

from __future__ import annotations

import csv
import json
import sys
from collections import defaultdict
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Iterable
from zoneinfo import ZoneInfo

REPO_ROOT = Path(__file__).resolve().parents[2]
BACKEND_DIR = REPO_ROOT / "apps" / "qwen_trade_software" / "backend"
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

# Lazy: JSONL helpers work without MT5 / tzdata installed.
mt5 = None  # type: ignore
_connect_mt5 = None
_NY = None


def _require_mt5():
    global mt5, _connect_mt5
    if mt5 is None:
        import MetaTrader5 as _mt5  # noqa: WPS433

        from review_shared import connect_mt5 as _cm  # noqa: WPS433

        mt5 = _mt5
        _connect_mt5 = _cm
    return mt5


def connect_mt5():
    _require_mt5()
    assert _connect_mt5 is not None
    return _connect_mt5()


def _ny() -> ZoneInfo:
    global _NY
    if _NY is None:
        _NY = ZoneInfo("America/New_York")
    return _NY

TIMEFRAME_SECONDS = {
    "M1": 60,
    "M5": 300,
    "M15": 900,
    "M30": 1800,
    "H1": 3600,
    "H4": 14400,
}

def _mt5_timeframes() -> dict[str, int]:
    m = _require_mt5()
    return {"M1": m.TIMEFRAME_M1, "H1": m.TIMEFRAME_H1}

CANDLE_COLUMNS = [
    "symbol",
    "timeframe",
    "time_utc",
    "open",
    "high",
    "low",
    "close",
    "tick_volume",
    "spread",
    "real_volume",
    "source",
    "derived_from",
    "bar_timezone",
]

TICK_COLUMNS = [
    "symbol",
    "time_utc",
    "time_msc",
    "bid",
    "ask",
    "last",
    "volume",
    "flags",
    "source",
]


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def iso_utc(value: datetime) -> str:
    if value.tzinfo is None:
        value = value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def parse_utc(value: str) -> datetime:
    if value.endswith("Z"):
        value = value[:-1] + "+00:00"
    return datetime.fromisoformat(value).astimezone(timezone.utc)


def month_key(value: datetime) -> str:
    return value.strftime("%Y-%m")


def day_key(value: datetime) -> str:
    return value.strftime("%Y-%m-%d")


def normalize_rate(symbol: str, timeframe: str, rate: Any, *, derived_from: str = "MT5", bar_timezone: str = "UTC") -> dict[str, Any]:
    opened = datetime.fromtimestamp(int(rate["time"]), timezone.utc)
    return {
        "symbol": symbol,
        "timeframe": timeframe,
        "time_utc": iso_utc(opened),
        "open": float(rate["open"]),
        "high": float(rate["high"]),
        "low": float(rate["low"]),
        "close": float(rate["close"]),
        "tick_volume": int(rate["tick_volume"]),
        "spread": int(rate["spread"]),
        "real_volume": int(rate["real_volume"]),
        "source": "MT5",
        "derived_from": derived_from,
        "bar_timezone": bar_timezone,
    }


def _tick_field(tick: Any, name: str, default: Any = 0) -> Any:
    try:
        return tick[name]
    except (TypeError, KeyError, IndexError):
        return getattr(tick, name, default)


def normalize_tick(symbol: str, tick: Any) -> dict[str, Any]:
    time_msc = int(_tick_field(tick, "time_msc", 0) or 0)
    tick_time = int(_tick_field(tick, "time", 0) or 0)
    ts = time_msc / 1000 if time_msc else tick_time
    opened = datetime.fromtimestamp(ts, timezone.utc)
    return {
        "symbol": symbol,
        "time_utc": iso_utc(opened),
        "time_msc": time_msc or int(ts * 1000),
        "bid": float(_tick_field(tick, "bid", 0.0)),
        "ask": float(_tick_field(tick, "ask", 0.0)),
        "last": float(_tick_field(tick, "last", 0.0) or 0.0),
        "volume": int(_tick_field(tick, "volume", 0) or 0),
        "flags": int(_tick_field(tick, "flags", 0) or 0),
        "source": "MT5",
    }


def ensure_symbol(symbol: str) -> None:
    m = _require_mt5()
    info = m.symbol_info(symbol)
    if info is None:
        raise RuntimeError(f"Symbol {symbol} not found: {m.last_error()}")
    if not info.visible and not m.symbol_select(symbol, True):
        raise RuntimeError(f"Could not select {symbol}: {m.last_error()}")


def probe_earliest_bar(symbol: str, timeframe: str) -> datetime | None:
    m = _require_mt5()
    mt5_tf = _mt5_timeframes().get(timeframe)
    if mt5_tf is None:
        raise ValueError(f"Unsupported probe timeframe: {timeframe}")

    if timeframe in {"M1", "H1"}:
        return _probe_earliest_via_pos(symbol, mt5_tf)

    start = datetime(2000, 1, 1, tzinfo=timezone.utc)
    end = utc_now()
    rates = m.copy_rates_range(symbol, mt5_tf, start, end)
    if rates is None or len(rates) == 0:
        return None
    return datetime.fromtimestamp(int(rates[0]["time"]), timezone.utc)


def _bar_time_at_pos(symbol: str, mt5_tf: int, pos: int) -> datetime | None:
    m = _require_mt5()
    rates = m.copy_rates_from_pos(symbol, mt5_tf, pos, 1)
    if rates is None or len(rates) == 0:
        return None
    return datetime.fromtimestamp(int(rates[0]["time"]), timezone.utc)


def _probe_earliest_via_pos(symbol: str, mt5_tf: int, max_search: int = 200_000) -> datetime | None:
    lo, hi = 0, max_search
    best: datetime | None = None
    while lo <= hi:
        mid = (lo + hi) // 2
        ts = _bar_time_at_pos(symbol, mt5_tf, mid)
        if ts is None:
            hi = mid - 1
        else:
            best = ts
            lo = mid + 1
    return best


def copy_m1_via_positions(
    symbol: str,
    start: datetime,
    end: datetime,
    *,
    chunk: int = 5000,
    max_search: int = 200_000,
) -> list[dict[str, Any]]:
    m = _require_mt5()
    mt5_tf = _mt5_timeframes()["M1"]
    lo, hi = 0, max_search
    max_pos = 0
    while lo <= hi:
        mid = (lo + hi) // 2
        if _bar_time_at_pos(symbol, mt5_tf, mid) is None:
            hi = mid - 1
        else:
            max_pos = mid
            lo = mid + 1

    rows: list[dict[str, Any]] = []
    pos = max_pos
    while pos >= 0:
        count = min(chunk, pos + 1)
        start_pos = pos - count + 1
        rates = m.copy_rates_from_pos(symbol, mt5_tf, start_pos, count)
        if rates is None:
            err = m.last_error()
            raise RuntimeError(f"copy_rates_from_pos M1 pos={start_pos} count={count} failed: {err}")
        for rate in rates:
            opened = datetime.fromtimestamp(int(rate["time"]), timezone.utc)
            if opened < start:
                continue
            if opened >= end:
                continue
            rows.append(normalize_rate(symbol, "M1", rate))
        pos = start_pos - 1
    rows.sort(key=lambda item: item["time_utc"])
    return rows


def probe_earliest_tick(symbol: str) -> datetime | None:
    m = _require_mt5()
    start = datetime(2000, 1, 1, tzinfo=timezone.utc)
    end = start + timedelta(days=1)
    while end <= utc_now():
        ticks = m.copy_ticks_range(symbol, start, end, m.COPY_TICKS_ALL)
        if ticks is not None and len(ticks) > 0:
            first = ticks[0]
            time_msc = int(_tick_field(first, "time_msc", 0) or 0)
            tick_time = int(_tick_field(first, "time", 0) or 0)
            ts = time_msc / 1000 if time_msc else tick_time
            return datetime.fromtimestamp(ts, timezone.utc)
        start = end
        end = min(end + timedelta(days=30), utc_now())
    return None


def copy_rates_chunk(symbol: str, timeframe: str, start: datetime, end: datetime) -> list[dict[str, Any]]:
    m = _require_mt5()
    mt5_tf = _mt5_timeframes()[timeframe]
    rates = m.copy_rates_range(symbol, mt5_tf, start, end)
    if rates is None:
        err = m.last_error()
        raise RuntimeError(f"copy_rates_range {timeframe} {start}..{end} failed: {err}")
    return [
        normalize_rate(symbol, timeframe, rate)
        for rate in sorted(rates, key=lambda item: int(item["time"]))
    ]


def copy_ticks_chunk(symbol: str, start: datetime, end: datetime, *, max_ticks: int = 100_000) -> list[dict[str, Any]]:
    if start >= end:
        return []
    m = _require_mt5()
    ticks = m.copy_ticks_range(symbol, start, end, m.COPY_TICKS_ALL)
    if ticks is None:
        err = m.last_error()
        raise RuntimeError(f"copy_ticks_range {start}..{end} failed: {err}")
    if len(ticks) >= max_ticks and (end - start) > timedelta(seconds=1):
        mid = start + (end - start) / 2
        left = copy_ticks_chunk(symbol, start, mid, max_ticks=max_ticks)
        right = copy_ticks_chunk(symbol, mid, end, max_ticks=max_ticks)
        return left + right
    return [normalize_tick(symbol, tick) for tick in ticks]


def write_csv(path: Path, columns: list[str], rows: Iterable[dict[str, Any]]) -> int:
    path.parent.mkdir(parents=True, exist_ok=True)
    count = 0
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=columns, extrasaction="ignore")
        writer.writeheader()
        for row in rows:
            writer.writerow(row)
            count += 1
    return count


def write_jsonl(path: Path, rows: Iterable[dict[str, Any]]) -> int:
    """Write one JSON object per line (UTF-8). Same rows as the paired CSV."""
    path.parent.mkdir(parents=True, exist_ok=True)
    count = 0
    with path.open("w", encoding="utf-8") as handle:
        for row in rows:
            handle.write(json.dumps(row, ensure_ascii=False) + "\n")
            count += 1
    return count


# Fib ratios from core_skill [fib-location] — location map only.
FIB_RATIOS = (0.236, 0.382, 0.5, 0.618, 0.786)
# TFs that get swing fib + floor pivots (distilled: H4/H1/D1 own location map).
LOCATION_MAP_TFS = frozenset({"H4", "H1", "D1"})
SWING_LOOKBACK = {"H4": 20, "H1": 40, "D1": 20, "M30": 0, "M15": 0, "M5": 0, "M1": 0}
VOLUME_MEDIAN_WINDOW = 20


def _f(row: dict[str, Any], key: str) -> float:
    return float(row[key])


def floor_pivot_map(high: float, low: float, close: float, prefix: str) -> dict[str, float]:
    """Floor pivots from completed bar — same family as live trade_management.chart_levels."""
    pp = (high + low + close) / 3.0
    return {
        f"{prefix}_FLOOR_PP": round(pp, 6),
        f"{prefix}_FLOOR_R1": round(2.0 * pp - low, 6),
        f"{prefix}_FLOOR_S1": round(2.0 * pp - high, 6),
        f"{prefix}_FLOOR_R2": round(pp + (high - low), 6),
        f"{prefix}_FLOOR_S2": round(pp - (high - low), 6),
    }


def fib_retracement_map(swing_high: float, swing_low: float, prefix: str) -> dict[str, float]:
    """Supplied fib location from completed swing (never a direction signal)."""
    span = swing_high - swing_low
    if span <= 0:
        return {}
    out = {
        f"{prefix}_SWING_HIGH": round(swing_high, 6),
        f"{prefix}_SWING_LOW": round(swing_low, 6),
    }
    for ratio in FIB_RATIOS:
        tag = str(ratio).replace("0.", "").ljust(3, "0")[:3]
        if ratio == 0.5:
            tag = "50"
        elif ratio == 0.236:
            tag = "236"
        elif ratio == 0.382:
            tag = "382"
        elif ratio == 0.618:
            tag = "618"
        elif ratio == 0.786:
            tag = "786"
        out[f"{prefix}_FIB_{tag}"] = round(swing_high - ratio * span, 6)
    return out


def _level_object(level_id: str, price: float, timeframe: str, role: str, method: str) -> dict[str, Any]:
    return {
        "level_id": level_id,
        "timeframe": timeframe,
        "zone_low": price,
        "zone_high": price,
        "role": role,
        "calculation_method": method,
    }


def volume_context(rows: list[dict[str, Any]], index: int) -> dict[str, Any]:
    """Tick-volume participation — matches live cache emphasis on tick_volume ratios."""
    cur = rows[index]
    tick_vol = int(float(cur.get("tick_volume") or 0))
    real_vol = int(float(cur.get("real_volume") or 0))
    start = max(0, index - VOLUME_MEDIAN_WINDOW + 1)
    window = [int(float(r.get("tick_volume") or 0)) for r in rows[start : index + 1]]
    ordered = sorted(window)
    mid = len(ordered) // 2
    if not ordered:
        median = 0.0
    elif len(ordered) % 2:
        median = float(ordered[mid])
    else:
        median = (ordered[mid - 1] + ordered[mid]) / 2.0
    ratio = round(tick_vol / median, 4) if median > 0 else None
    return {
        "tick_volume": tick_vol,
        "real_volume": real_vol,
        "tick_volume_median_20": median,
        "tick_volume_ratio": ratio,
        "spread": int(float(cur.get("spread") or 0)),
    }


def levels_for_candle(
    rows: list[dict[str, Any]],
    index: int,
    timeframe: str,
) -> tuple[dict[str, float], list[dict[str, Any]]]:
    """
    Deterministic levels for this TF at bar index (bar is completed).
    Uses prior completed bar for PREVIOUS_* — same idea as live build_levels.
    H4/H1/D1 also get floor pivots + swing fib (core_skill fib/pivot-location).
    LTF (M30..M1): prior high/low only (path/timing — no invent fib).
    """
    flat: dict[str, float] = {}
    objects: list[dict[str, Any]] = []
    if index < 1:
        return flat, objects

    prior = rows[index - 1]
    ph, pl = _f(prior, "high"), _f(prior, "low")
    flat[f"{timeframe}_PREVIOUS_HIGH"] = ph
    flat[f"{timeframe}_PREVIOUS_LOW"] = pl
    objects.append(_level_object(f"{timeframe}_PREVIOUS_HIGH", ph, timeframe, "previous_high", "latest_completed_candle"))
    objects.append(_level_object(f"{timeframe}_PREVIOUS_LOW", pl, timeframe, "previous_low", "latest_completed_candle"))

    if timeframe not in LOCATION_MAP_TFS:
        return flat, objects

    # Floor pivots from prior completed bar (advance location).
    piv = floor_pivot_map(ph, pl, _f(prior, "close"), timeframe)
    flat.update(piv)
    for lid, price in piv.items():
        role = lid.replace(f"{timeframe}_", "").lower()
        objects.append(_level_object(lid, price, timeframe, role, "floor_pp_hlc3"))

    lookback = SWING_LOOKBACK.get(timeframe, 0)
    if lookback > 0 and index >= 2:
        # Swing from completed history before current bar (exclude current).
        window = rows[max(0, index - lookback) : index]
        if len(window) >= 2:
            swing_high = max(_f(r, "high") for r in window)
            swing_low = min(_f(r, "low") for r in window)
            fibs = fib_retracement_map(swing_high, swing_low, timeframe)
            flat.update(fibs)
            for lid, price in fibs.items():
                role = "swing" if "SWING" in lid else "fib_location"
                objects.append(
                    _level_object(lid, price, timeframe, role, f"swing_lookback_{lookback}")
                )
    return flat, objects


def enrich_candle_rows_for_jsonl(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """CSV stays OHLC+volume; JSONL adds levels + volume context for model prep."""
    if not rows:
        return []
    timeframe = str(rows[0].get("timeframe") or "M1")
    enriched: list[dict[str, Any]] = []
    for i, row in enumerate(rows):
        levels_flat, level_objects = levels_for_candle(rows, i, timeframe)
        vol = volume_context(rows, i)
        item = dict(row)
        # Keep top-level tick_volume for compatibility; nest full volume block.
        item["volume"] = vol
        item["levels"] = levels_flat
        item["level_objects"] = level_objects
        enriched.append(item)
    return enriched


def enrich_tick_rows_for_jsonl(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Ticks: explicit volume/spread; levels live on candle JSONL per TF."""
    enriched: list[dict[str, Any]] = []
    for row in rows:
        bid = float(row.get("bid") or 0)
        ask = float(row.get("ask") or 0)
        item = dict(row)
        item["volume"] = {
            "tick_print_volume": float(row.get("volume") or 0),
            "spread": round(ask - bid, 6) if ask and bid else None,
            "bid": bid,
            "ask": ask,
        }
        item["levels"] = {}
        item["level_note"] = "levels_attached_on_candle_jsonl_per_timeframe"
        enriched.append(item)
    return enriched


def write_csv_and_jsonl(
    csv_path: Path,
    columns: list[str],
    rows: list[dict[str, Any]],
    *,
    kind: str = "candle",
) -> int:
    """Side-by-side CSV + enriched JSONL (levels + volume on candle jsonl)."""
    count = write_csv(csv_path, columns, rows)
    jsonl_path = csv_path.with_suffix(".jsonl")
    if kind == "tick":
        jsonl_rows = enrich_tick_rows_for_jsonl(rows)
    else:
        jsonl_rows = enrich_candle_rows_for_jsonl(rows)
    write_jsonl(jsonl_path, jsonl_rows)
    return count


def write_type_examples(out_dir: Path) -> Path:
    """One short enriched JSONL example per market data type under out_dir/examples/."""
    examples_dir = out_dir / "examples"
    examples_dir.mkdir(parents=True, exist_ok=True)

    # Synthetic 3-bar series so PREVIOUS_* + fib/pivots populate.
    def _bars(tf: str, derived: str, tz: str) -> list[dict[str, Any]]:
        base = 2650.0
        out: list[dict[str, Any]] = []
        for i, (o, h, l, c, vol) in enumerate(
            [
                (base, base + 8, base - 2, base + 5, 800),
                (base + 5, base + 12, base + 1, base + 3, 1500),
                (base + 3, base + 6, base - 4, base + 1, 1100),
            ]
        ):
            out.append(
                {
                    "symbol": "XAUUSDr",
                    "timeframe": tf,
                    "time_utc": f"2026-08-01T{10+i:02d}:00:00Z",
                    "open": o,
                    "high": h,
                    "low": l,
                    "close": c,
                    "tick_volume": vol,
                    "spread": 16,
                    "real_volume": 0,
                    "source": "MT5" if derived == "MT5" else "derived",
                    "derived_from": derived,
                    "bar_timezone": tz,
                }
            )
        return out

    tick_rows = [
        {
            "symbol": "XAUUSDr",
            "time_utc": "2026-08-01T12:00:00Z",
            "time_msc": 1754056800123,
            "bid": 2650.12,
            "ask": 2650.28,
            "last": 0.0,
            "volume": 0,
            "flags": 6,
            "source": "MT5",
        }
    ]
    write_jsonl(examples_dir / "tick.example.jsonl", enrich_tick_rows_for_jsonl(tick_rows))

    for tf in ("M1", "M5", "M15", "M30", "H1", "H4"):
        derived = "MT5" if tf in ("M1", "H1") else ("H1" if tf == "H4" else "M1")
        tz = "America/New_York" if tf == "H4" else "UTC"
        series = _bars(tf, derived, tz)
        # Write last bar only as the "example" line (fully enriched).
        enriched = enrich_candle_rows_for_jsonl(series)
        write_jsonl(examples_dir / f"candle_{tf}.example.jsonl", [enriched[-1]])
    return examples_dir


def append_log(log_path: Path, record: dict[str, Any]) -> None:
    log_path.parent.mkdir(parents=True, exist_ok=True)
    with log_path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(record, ensure_ascii=True) + "\n")


def read_candles_csv(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    with path.open("r", encoding="utf-8", newline="") as handle:
        return list(csv.DictReader(handle))


def floor_utc(ts: datetime, seconds: int) -> datetime:
    epoch = int(ts.timestamp())
    floored = epoch - (epoch % seconds)
    return datetime.fromtimestamp(floored, timezone.utc)


def resample_utc(rows: list[dict[str, Any]], target_tf: str, *, derived_from: str) -> list[dict[str, Any]]:
    if not rows:
        return []
    seconds = TIMEFRAME_SECONDS[target_tf]
    buckets: dict[datetime, list[dict[str, Any]]] = defaultdict(list)
    for row in rows:
        ts = parse_utc(row["time_utc"])
        buckets[floor_utc(ts, seconds)].append(row)

    out: list[dict[str, Any]] = []
    for bucket_start in sorted(buckets):
        group = sorted(buckets[bucket_start], key=lambda item: item["time_utc"])
        first = group[0]
        out.append(
            {
                "symbol": first["symbol"],
                "timeframe": target_tf,
                "time_utc": iso_utc(bucket_start),
                "open": float(first["open"]),
                "high": max(float(item["high"]) for item in group),
                "low": min(float(item["low"]) for item in group),
                "close": float(group[-1]["close"]),
                "tick_volume": sum(int(item["tick_volume"]) for item in group),
                "spread": int(group[-1]["spread"]),
                "real_volume": sum(int(item["real_volume"]) for item in group),
                "source": "derived",
                "derived_from": derived_from,
                "bar_timezone": "UTC",
            }
        )
    return out


def h4_ny_bucket_start(open_utc: datetime) -> datetime:
    ny = open_utc.astimezone(_ny())
    bucket_hour = (ny.hour // 4) * 4
    bucket_ny = ny.replace(hour=bucket_hour, minute=0, second=0, microsecond=0)
    return bucket_ny.astimezone(timezone.utc)


def resample_h4_ny_from_h1(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    if not rows:
        return []
    buckets: dict[datetime, list[dict[str, Any]]] = defaultdict(list)
    for row in rows:
        ts = parse_utc(row["time_utc"])
        buckets[h4_ny_bucket_start(ts)].append(row)

    out: list[dict[str, Any]] = []
    for bucket_start in sorted(buckets):
        group = sorted(buckets[bucket_start], key=lambda item: item["time_utc"])
        first = group[0]
        out.append(
            {
                "symbol": first["symbol"],
                "timeframe": "H4",
                "time_utc": iso_utc(bucket_start),
                "open": float(first["open"]),
                "high": max(float(item["high"]) for item in group),
                "low": min(float(item["low"]) for item in group),
                "close": float(group[-1]["close"]),
                "tick_volume": sum(int(item["tick_volume"]) for item in group),
                "spread": int(group[-1]["spread"]),
                "real_volume": sum(int(item["real_volume"]) for item in group),
                "source": "derived",
                "derived_from": "H1",
                "bar_timezone": "America/New_York",
            }
        )
    return out


@dataclass
class ExportStats:
    rows: int = 0
    files: int = 0
    skipped: int = 0


def month_range(start: datetime, end: datetime) -> list[tuple[datetime, datetime]]:
    cursor = start.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    ranges: list[tuple[datetime, datetime]] = []
    while cursor < end:
        if cursor.month == 12:
            nxt = cursor.replace(year=cursor.year + 1, month=1)
        else:
            nxt = cursor.replace(month=cursor.month + 1)
        chunk_start = max(cursor, start)
        chunk_end = min(nxt, end)
        if chunk_start < chunk_end:
            ranges.append((chunk_start, chunk_end))
        cursor = nxt
    return ranges


def day_range(start: datetime, end: datetime) -> list[tuple[datetime, datetime]]:
    cursor = start.replace(hour=0, minute=0, second=0, microsecond=0)
    ranges: list[tuple[datetime, datetime]] = []
    while cursor < end:
        nxt = cursor + timedelta(days=1)
        chunk_start = max(cursor, start)
        chunk_end = min(nxt, end)
        if chunk_start < chunk_end:
            ranges.append((chunk_start, chunk_end))
        cursor = nxt
    return ranges


def shutdown_mt5() -> None:
    m = _require_mt5()
    m.shutdown()
