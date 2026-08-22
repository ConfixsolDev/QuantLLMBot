from market_intelligence.store import IntelligenceStore
from market_intelligence import trade_journal
from market_intelligence.trade_journal import build_journal, journal_closed_trade
import trade_journal_worker


def proposal():
    return {
        "symbol": "XAUUSDr",
        "qwen": {
            "model": "qwen-test",
            "confidence": 65,
            "summary": "Buy mapped support rejection",
            "execution_plan": {
                "side": "buy", "reason": "closed M1 rejection",
                "structure_timeframe": "M30",
                "entry_low": 100.0, "entry_high": 101.0,
                "optimal_entry_price": 101.0,
                "zone_edge_context": {"optimal_entry_price": 98.0},
                "cache_evidence_ids": ["candle:M1:1"],
            },
        },
    }


def losing_close():
    return {
        "event": "mt5_execution_closed",
        "proposal_id": "paper-test-loss",
        "execution_id": "demo-test-loss",
        "created_at_utc": "2026-08-21T06:58:05+00:00",
        "reason": "managed_or_safety_sl",
        "exit_price": 97.0,
        "average_entry": 100.0,
        "gross_pnl": -100.0,
        "costs": -2.0,
        "net_pnl": -102.0,
        "peak_pnl": 50.0,
        "maximum_drawdown": -110.0,
        "peak_favorable_price_move": 1.5,
        "adverse_price_move": 3.0,
        "price_giveback": 4.5,
        "position_holding_seconds": 300,
        "close_comments": ["[sl 97.0]"],
        "attribution_source": "broker_comment",
        "manager_close_decision": None,
        "pnl_is_complete": True,
        "fills": [{
            "order": None, "price": 100.0, "volume": 0.5,
            "filled_at_utc": "2026-08-21T06:53:05+00:00",
            "stop_loss": 97.0, "take_profit": 105.0,
            "sl_source": "fixed_3_5_after_geometry:reward_risk_too_low",
        }],
    }


def test_builds_evidence_based_loss_postmortem():
    journal = build_journal(losing_close(), proposal())
    assert journal["result"] == "loss"
    assert journal["peak_pnl"] == 50.0
    assert journal["secured_cash"] == 0.0
    assert "structural_geometry_rejected_fallback" in journal["loss_reasons_json"]
    assert "favorable_excursion_not_secured" in journal["loss_reasons_json"]
    assert "entry_edge_mismatch" in journal["loss_reasons_json"]


def test_sqlite_journal_is_idempotent(tmp_path):
    path = tmp_path / "journal.sqlite3"
    journal_closed_trade(losing_close(), proposal(), path)
    journal_closed_trade(losing_close(), proposal(), path)
    store = IntelligenceStore(path)
    try:
        rows = store.trade_journals()
        assert len(rows) == 1
        assert rows[0]["idea_summary"] == "Buy mapped support rejection"
        assert rows[0]["loss_reasons"]
        assert rows[0]["qwen_analysis_status"] == "pending"
    finally:
        store.db.close()


def test_secured_cash_is_derived_from_accepted_stop_update(tmp_path, monkeypatch):
    protection = tmp_path / "profit-protection-2026-08-21.jsonl"
    protection.write_text(
        '{"timestamp_utc":"2026-08-21T06:55:00Z","event":"stop_update",'
        '"ticket":123,"retcode":10009,"requested_stop":100.3,'
        '"locked_move":0.3,"volume":0.5}\n',
        encoding="utf-8",
    )
    monkeypatch.setattr(trade_journal, "LOG_DIR", tmp_path)
    secured = trade_journal._secured([{"order": 123}], "2026-08-21")
    assert round(secured["cash"], 2) == 15.0
    assert secured["stop"] == 100.3


def test_qwen_analysis_is_added_as_second_stage(tmp_path, monkeypatch):
    path = tmp_path / "journal.sqlite3"
    journal_closed_trade(losing_close(), proposal(), path)
    store = IntelligenceStore(path)
    monkeypatch.setattr(
        trade_journal_worker,
        "ollama_generate",
        lambda *args, **kwargs: {"response": '{"summary":"Reversal after entry",'
            '"entry_assessment":"Late","management_assessment":"No lock",'
            '"what_worked":["Initial response"],"what_failed":["Giveback"],'
            '"likely_loss_reasons":["Poor geometry"],"lesson":"Require geometry",'
            '"confidence":90}'},
    )
    try:
        row = store.pending_trade_journals(1)[0]
        trade_journal_worker.analyze_one(store, row, model="qwen-test")
        saved = store.db.execute(
            "SELECT qwen_analysis_status,qwen_analysis_json,qwen_analysis_model "
            "FROM trade_journal WHERE proposal_id=?", ("paper-test-loss",)
        ).fetchone()
        assert saved["qwen_analysis_status"] == "complete"
        assert "Poor geometry" in saved["qwen_analysis_json"]
        assert saved["qwen_analysis_model"] == "qwen-test"
    finally:
        store.db.close()


def test_qwen_cannot_omit_loss_facts_or_claim_trade_was_not_executed(tmp_path, monkeypatch):
    path = tmp_path / "journal.sqlite3"
    journal_closed_trade(losing_close(), proposal(), path)
    store = IntelligenceStore(path)
    monkeypatch.setattr(
        trade_journal_worker,
        "ollama_generate",
        lambda *args, **kwargs: {"response": '{"summary":"not traded",'
            '"entry_assessment":"not_traded","management_assessment":"not traded",'
            '"what_worked":[],"what_failed":[],"likely_loss_reasons":[],'
            '"lesson":"Review","confidence":70}'},
    )
    try:
        row = store.pending_trade_journals(1)[0]
        analysis = trade_journal_worker.analyze_one(store, row, model="qwen-test")
        assert analysis["what_failed"]
        assert analysis["likely_loss_reasons"]
        assert all(not reason.startswith("{") for reason in analysis["what_failed"])
        assert all("not traded" not in analysis[key].lower() for key in (
            "summary", "entry_assessment", "management_assessment"
        ))
    finally:
        store.db.close()
