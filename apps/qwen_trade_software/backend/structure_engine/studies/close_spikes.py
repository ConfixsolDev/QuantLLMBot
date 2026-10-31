"""Close-spike study: what happens after an M1 burst into an H1/H4 close?

Reads a back-test's ``events.jsonl`` (structure_engine.runner backtest), joins
every ``close_spike`` with its ``close_spike_outcome`` labels and prints base
rates: how often the spike REVERSED, CONTINUED or ended PARTIAL after each
horizon, overall and split by context.

    python -m structure_engine.studies.close_spikes runs/real/events.jsonl
    python -m structure_engine.studies.close_spikes runs/real/events.jsonl --json spikes_report.json --csv spikes.csv

How to read it
--------------
* ``n`` is the number of spikes in the group. Small groups (n < 30) are
  shown but marked: a percentage from 8 events is an anecdote, not a rate.
* ``rev% / cont% / part%`` are shares of that group at that horizon.
* ``run`` = median distance price ran beyond the spike extreme afterwards;
  ``retr`` = median deepest retrace back from the extreme; both in units of
  the spike's own size (1.0 = a full spike length).
* Splits answer the hypotheses directly: did spikes that CLOSED HELD (no
  wick) continue more than REJECTED ones? Do spikes that swept a session
  level or the previous candle reverse more? Do spikes WITH the H4 trend
  continue more than spikes AGAINST it?

This is research output. A base rate here becomes a trading rule only through
the change process in the architecture doc (Part A6).
"""

from __future__ import annotations

import argparse
import csv
import json
import statistics
from collections import defaultdict
from pathlib import Path

LABELS = ("reversal", "continuation", "partial")


def load(events_path: str | Path) -> tuple[list[dict], dict[str, dict[int, dict]], list[int]]:
    """Spikes (one dict each), their outcomes {spike_id: {horizon: label}}, horizons."""
    spikes: list[dict] = []
    outcomes: dict[str, dict[int, dict]] = defaultdict(dict)
    with open(events_path, encoding="utf-8") as fh:
        for line in fh:
            e = json.loads(line)
            if e["kind"] == "close_spike":
                spikes.append({"tf": e["tf"], **e["data"]})
            elif e["kind"] == "close_spike_outcome":
                outcomes[e["data"]["spike_id"]][e["data"]["horizon_minutes"]] = e["data"]
    horizons = sorted({h for hs in outcomes.values() for h in hs})
    return spikes, outcomes, horizons


def _context(row: dict) -> dict[str, str]:
    """Named, coarse context buckets for the split tables."""
    trend = row.get("htf_trend", "mixed")
    with_trend = ("with_trend" if (trend == "up") == (row["direction"] == "up") else "against_trend") \
        if trend in ("up", "down") else "trend_mixed"
    return {
        "tf_dir": f"{row['tf']} {row['direction']}",
        "close": "held" if row.get("held") else "rejected",
        "prev_candle": "swept_prev" if row.get("swept_prev") else "inside_prev",
        "levels": "swept_level" if row.get("swept_levels") else "no_level",
        "zone": "at_zone" if row.get("at_zone") else "no_zone",
        "h4_trend": with_trend,
        "session": row.get("session") or "off_session",
    }


def report(rows: list[dict], outcomes: dict, horizons: list[int]) -> dict:
    groups: dict[tuple[str, str], list[dict]] = defaultdict(list)
    for r in rows:
        groups[("all", "all")].append(r)
        for k, v in _context(r).items():
            groups[(k, v)].append(r)
    table = {}
    for key, members in sorted(groups.items()):
        entry = {"n": len(members)}
        for h in horizons:
            labs = [outcomes.get(r["spike_id"], {}).get(h) for r in members]
            labs = [x for x in labs if x]
            if not labs:
                continue
            cnt = {lab: sum(1 for x in labs if x["label"] == lab) for lab in LABELS}
            entry[str(h)] = {
                "n": len(labs),
                **{f"{lab}_pct": round(100 * cnt[lab] / len(labs), 1) for lab in LABELS},
                "median_run_beyond": round(statistics.median(x["run_beyond_extreme"] for x in labs), 3),
                "median_max_retrace": round(statistics.median(x["max_retrace"] for x in labs), 3),
            }
        table[f"{key[0]}={key[1]}"] = entry
    return table


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("events")
    ap.add_argument("--json", default=None)
    ap.add_argument("--csv", default=None, help="one row per spike with its labels")
    args = ap.parse_args()

    rows, outcomes_by_spike, horizons = load(args.events)
    table = report(rows, outcomes_by_spike, horizons)

    print(f"Close-spike study: {len(rows)} spikes, horizons {horizons} min  (* = n < 30, treat as anecdote)")
    head = f"{'group':<30}{'n':>5}" + "".join(f"{'h' + str(h) + ' rev/cont/part':>24}" for h in horizons)
    print(head)
    for name, e in table.items():
        cells = ""
        for h in horizons:
            x = e.get(str(h))
            cells += f"{'-':>24}" if not x else f"{x['reversal_pct']:>9.0f}/{x['continuation_pct']:.0f}/{x['partial_pct']:.0f}".rjust(24)
        print(f"{name:<30}{e['n']:>5}{'*' if e['n'] < 30 else ' '}{cells}")
    if args.json:
        Path(args.json).write_text(json.dumps({"spikes": len(rows), "horizons": horizons, "table": table}, indent=1))
    if args.csv:
        with open(args.csv, "w", newline="", encoding="utf-8") as fh:
            w = csv.writer(fh)
            w.writerow(["tf", "close_time", "direction", "move", "move_atr", "held", "swept_prev",
                        "swept_level", "at_zone", "htf_trend", "session", "volume_ratio"]
                       + [f"label_{h}" for h in horizons])
            for r in rows:
                labs = outcomes_by_spike.get(r["spike_id"], {})
                w.writerow([r["tf"], r["close_time"], r["direction"], r["move"], r["move_atr"], r["held"],
                            r["swept_prev"], bool(r["swept_levels"]), bool(r["at_zone"]), r["htf_trend"],
                            r["session"], r["volume_ratio"]]
                           + [labs.get(h, {}).get("label") for h in horizons])


if __name__ == "__main__":
    main()
