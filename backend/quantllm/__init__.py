"""QuantLLM application: MT5 data -> database -> structure engine -> API -> website.

Modules
-------
settings.py        database / API / history settings (config/app.json + env)
mt5_connection.py  the one place that says how to reach MT5 (config/mt5_connection.json)
database.py        PostgreSQL / TimescaleDB: M1 candles, structure events, state
market_feed.py     closed M1 bars from MT5 history, MT5 live polling, CSV files
overlays.py        engine events -> chart drawings (lines, boxes, markers, levels)
service.py         the running service and its HTTP API
__main__.py        command line: serve | check | import-csv | import-mt5

No Qwen and no trading here: this application only reads the market and
shows what the deterministic structure engine sees.
"""
