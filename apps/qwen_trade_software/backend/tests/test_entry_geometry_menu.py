from __future__ import annotations

import entry_contract
from entry_geometry_menu import build_geometry_menu, schema_level_roles


def test_menu_exposes_valid_geometry_without_selecting_a_trade():
    levels = [
        {"id": "H1_LOWER", "lo": 90.0, "hi": 91.0},
        {"id": "M15_BUY_ANCHOR", "lo": 100.0, "hi": 101.0},
        {"id": "M15_SELL_ANCHOR", "lo": 110.0, "hi": 111.0},
        {"id": "H1_UPPER", "lo": 120.0, "hi": 121.0},
    ]
    responses = [
        {"level_id": "M15_BUY_ANCHOR", "direction": "buy", "confirmed": True,
         "state": "probe_rejection", "candle_id": "buy-candle"},
        {"level_id": "M15_SELL_ANCHOR", "direction": "sell", "confirmed": True,
         "state": "probe_rejection", "candle_id": "sell-candle"},
    ]
    menu = build_geometry_menu(levels, responses)
    assert {row["side"] for row in menu} == {"buy", "sell"}
    buy = next(row for row in menu if row["side"] == "buy")
    sell = next(row for row in menu if row["side"] == "sell")
    assert buy["valid_stop_level_ids"] == ["H1_LOWER"]
    assert buy["valid_target_level_ids"] == ["M15_SELL_ANCHOR", "H1_UPPER"]
    assert sell["valid_stop_level_ids"] == ["H1_UPPER"]
    assert sell["valid_target_level_ids"] == ["M15_BUY_ANCHOR", "H1_LOWER"]


def test_menu_rejects_m1_and_m5_as_trade_locations():
    levels = [
        {"id": "M15_LOWER", "price": 90.0},
        {"id": "M1_PREVIOUS_HIGH", "price": 100.0},
        {"id": "M5_PREVIOUS_HIGH", "price": 101.0},
        {"id": "H1_UPPER", "price": 110.0},
    ]
    responses = [
        {"level_id": "M1_PREVIOUS_HIGH", "direction": "sell", "confirmed": True},
        {"level_id": "M5_PREVIOUS_HIGH", "direction": "sell", "confirmed": True},
    ]

    assert build_geometry_menu(levels, responses) == []


def test_every_entry_stop_and_target_is_owned_by_m15_or_above():
    levels = [
        {"id": "M1_LOWER", "price": 85.0},
        {"id": "M15_LOWER", "price": 90.0},
        {"id": "H1_BUY_ANCHOR", "price": 100.0},
        {"id": "M5_UPPER", "price": 106.0},
        {"id": "M30_UPPER", "price": 110.0},
    ]
    responses = [{
        "level_id": "H1_BUY_ANCHOR", "direction": "buy", "confirmed": True,
    }]

    menu = build_geometry_menu(levels, responses)

    assert menu[0]["valid_stop_level_ids"] == ["M15_LOWER"]
    assert menu[0]["valid_target_level_ids"] == ["M30_UPPER"]


def test_wire_schema_separates_entry_stop_and_target_roles():
    menu = [{
        "geometry_row_id": "G1",
        "side": "sell", "entry_low_id": "ENTRY", "entry_high_id": "ENTRY",
        "valid_stop_level_ids": ["STOP"],
        "valid_target_level_ids": ["TARGET"],
    }]
    roles = schema_level_roles(menu)
    schema = entry_contract.build_schema(
        epochs={"minute": "m1"},
        level_ids=["ENTRY", "STOP", "TARGET", "WRONG"],
        evidence_ids=["candle-1"],
        entry_level_ids=roles["entry"],
        stop_level_ids=roles["stop"],
        target_level_ids=roles["target"],
        geometry_menu=menu,
    )
    props = schema["properties"]
    assert props["geometry_row_id"]["enum"] == ["G1", "__none__"]
    assert "entry_low_id" not in props
