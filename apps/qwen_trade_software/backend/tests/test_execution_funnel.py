import json

from execution_funnel import build_funnel


def _append_jsonl(path, rows):
    path.write_text(
        "".join(json.dumps(row) + "\n" for row in rows),
        encoding="utf-8",
    )


def test_closed_results_are_deduplicated_and_require_real_fills(tmp_path):
    day = "2026-08-24"
    _append_jsonl(
        tmp_path / f"paper-executions-{day}.jsonl",
        [
            {
                "event": "mt5_execution_started",
                "proposal_id": "loss",
            },
            {
                "event": "mt5_fill",
                "proposal_id": "loss",
            },
            {
                "event": "mt5_execution_started",
                "proposal_id": "partial-then-reconciled",
            },
            {
                "event": "mt5_fill",
                "proposal_id": "partial-then-reconciled",
            },
            {
                "event": "mt5_execution_closed",
                "proposal_id": "refused",
                "fills": [],
                "pnl_is_complete": True,
                "net_pnl": -999.0,
            },
            {
                "event": "mt5_execution_closed",
                "proposal_id": "loss",
                "fills": [{"ticket": 1}],
                "pnl_is_complete": True,
                "net_pnl": -151.13,
            },
            {
                "event": "mt5_execution_closed",
                "proposal_id": "partial-then-reconciled",
                "fills": [{"ticket": 2}],
                "pnl_is_complete": True,
                "net_pnl": 15.79,
            },
            {
                "event": "mt5_execution_closed",
                "proposal_id": "partial-then-reconciled",
                "fills": [{"ticket": 2}],
                "pnl_is_complete": True,
                "net_pnl": 99.99,
            },
        ],
    )

    funnel = build_funnel(tmp_path, day=day)

    assert funnel.closed_trades == 2
    assert funnel.wins == 1
    assert funnel.net_pnl == -51.14
    assert funnel.headline == "2 trades closed · 1W/1L · net -51.14"
    assert [(stage.name, stage.count) for stage in funnel.stages[-3:]] == [
        ("Entry attempted", 2),
        ("Filled", 2),
        ("Closed", 2),
    ]


def test_incomplete_close_is_not_reported_as_realised(tmp_path):
    day = "2026-08-24"
    _append_jsonl(
        tmp_path / f"paper-executions-{day}.jsonl",
        [
            {
                "event": "mt5_execution_closed",
                "proposal_id": "still-open",
                "fills": [{"ticket": 3}],
                "pnl_is_complete": False,
                "net_pnl": 12.0,
            }
        ],
    )

    funnel = build_funnel(tmp_path, day=day)

    assert funnel.closed_trades == 0
    assert funnel.net_pnl is None
