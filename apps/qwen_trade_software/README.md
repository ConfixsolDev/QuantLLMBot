# QuantLLM vNext Trading Application

This application tree contains only the clean vNext implementation governed by
`../../XAUUSD_SYSTEM_ARCHITECTURE_V2.md`.

- `vnext/` contains common runtime, intelligence, strategy, risk, persistence,
  execution, recovery, replay, and tests.
- `vnext/web/` is the read-only V2 operations dashboard. Start it with
  `../../deploy/Start-QuantLLMVNext-Web.ps1`; it binds only to localhost and
  reads the immutable V2 event ledger.
- `.venv/` is the local Python runtime used by vNext operational scripts.
- `../../deploy/Start-QuantLLMVNext.ps1` performs fail-closed infrastructure and
  broker reconciliation preflight. Production execution remains paused until
  the architecture activation gates are satisfied.

Run the test suite from this directory:

```powershell
& .\.venv\Scripts\python.exe -m pytest vnext -q
```

Retired implementations and their historical artifacts are quarantined under
`../../remove/` and are not part of the active system.
