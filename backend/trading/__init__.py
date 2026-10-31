"""Module 3 — trading: from an approved, triggered plan to a recorded result.

    intent.py     TradeIntent — the only thing that crosses from decision to execution
    settings.py   config/trading.json (risk %, magic, mode off / paper / demo)
    risk.py       position size = % of balance per stop distance (broker values)
    broker.py     MT5Broker (demo account) and PaperBroker (replays, tests)
    executor.py   checks -> one market order with stop + target -> trade life -> result in R
    journal.py    decisions / trades / refusals tables in TimescaleDB (or memory)
    pipeline.py   the bar-by-bar decision loop (same for replay and live)
    backtest.py   python -m trading.backtest — replay lanes: take-all vs Qwen

Demo only: the executor refuses a live account, and the settings refuse
``require_demo: false``. See V3 Part F.
"""
