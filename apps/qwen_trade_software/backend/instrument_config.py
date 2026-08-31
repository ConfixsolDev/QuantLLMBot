"""Instrument identity, analysis tuning, and explicit execution permission."""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True, slots=True)
class InstrumentConfig:
    key: str
    broker_symbol: str
    aliases: tuple[str, ...] = ()
    digits: int = 3
    analysis_round_digits: int = 1
    point_size: float = 0.001
    fvg_min_width: float = 0.3
    ote_min_impulse: float = 3.0
    equal_level_tolerance: float = 1.0
    sweep_overshoot_max: float = 2.0
    order_block_touch_tolerance: float = 0.2
    displacement_min_body: float = 1.5
    mapped_level_max_distance: float = 30.0
    prompt_section: str | None = None
    trade_enabled: bool = False
    context_only: bool = True
    contract_value_per_price_unit_lot: float = 1.0
    zone_stop_buffer: float = 0.0003
    scoring_min_rr: float = 1.5
    scoring_strong_rr: float = 3.0
    scoring_strong_departure_atr: float = 2.0
    scoring_moderate_departure_atr: float = 1.25
    min_stop_by_timeframe: dict[str, float] = field(default_factory=dict)
    min_target_by_timeframe: dict[str, float] = field(default_factory=dict)
    default_min_stop: float = 0.001
    default_min_target: float = 0.001
    maximum_stop_distance: float = 0.1
    minimum_stop_distance: float = 0.0001
    structure_buffer_fraction: float = 0.15
    minimum_structure_buffer: float = 0.0003
    round_trip_cost: float = 0.0002
    fallback_stop_distance: float = 0.003
    fallback_target_distance: float = 0.005
    timeframe_bars: dict[str, int] = field(default_factory=lambda: {
        "M5": 50, "M15": 40, "H1": 30, "H4": 20,
    })

    def accepts(self, symbol: str) -> bool:
        value = str(symbol or "").upper()
        return value in {self.key.upper(), self.broker_symbol.upper(), *(
            alias.upper() for alias in self.aliases
        )}


XAUUSD = InstrumentConfig(
    key="XAUUSD",
    broker_symbol="XAUUSDr",
    aliases=("GOLD",),
    prompt_section="instrument_xauusd",
    trade_enabled=True,
    context_only=False,
    contract_value_per_price_unit_lot=100.0,
    zone_stop_buffer=1.5,
    scoring_strong_departure_atr=2.5,
    scoring_moderate_departure_atr=1.5,
    min_stop_by_timeframe={
        "M1": 3.0, "M5": 4.0, "M15": 5.0, "M30": 5.0,
        "H1": 7.0, "H4": 10.0, "D1": 10.0,
    },
    min_target_by_timeframe={
        # Gold scalps use the same five-point minimum on every timeframe;
        # higher timeframes may improve the target, but may not reject a
        # valid five-point opportunity solely because of their label.
        "M1": 5.0, "M5": 5.0, "M15": 5.0, "M30": 5.0,
        "H1": 5.0, "H4": 5.0, "D1": 5.0,
    },
    default_min_stop=5.0,
    default_min_target=5.0,
    maximum_stop_distance=25.0,
    minimum_stop_distance=1.0,
    minimum_structure_buffer=0.3,
    round_trip_cost=0.2,
    fallback_stop_distance=3.0,
    fallback_target_distance=5.0,
)

_INSTRUMENTS: dict[str, InstrumentConfig] = {}


def register_instrument(config: InstrumentConfig) -> None:
    for name in (config.key, config.broker_symbol, *config.aliases):
        _INSTRUMENTS[name.upper()] = config


def instrument_for(symbol: str) -> InstrumentConfig:
    """Return registered tuning, or safe scale-derived generic defaults."""
    key = str(symbol or "").strip()
    if not key:
        raise ValueError("instrument symbol is required")
    known = _INSTRUMENTS.get(key.upper())
    if known is not None:
        return known
    # Unknown markets can be analysed immediately, while callers may register
    # more precise tuning before production qualification.
    return InstrumentConfig(
        key=key.upper(), broker_symbol=key, aliases=(), digits=5,
        analysis_round_digits=5,
        point_size=0.00001, fvg_min_width=0.0003,
        ote_min_impulse=0.003, equal_level_tolerance=0.001,
        sweep_overshoot_max=0.002, order_block_touch_tolerance=0.0002,
        displacement_min_body=0.0015, mapped_level_max_distance=0.03,
        trade_enabled=False, context_only=True,
        contract_value_per_price_unit_lot=1.0,
        zone_stop_buffer=0.0003,
        min_stop_by_timeframe={
            "M1": 0.0003, "M5": 0.0004, "M15": 0.0005,
            "M30": 0.0005, "H1": 0.0007, "H4": 0.001, "D1": 0.001,
        },
        min_target_by_timeframe={
            "M1": 0.0003, "M5": 0.0004, "M15": 0.0005,
            "M30": 0.0005, "H1": 0.001, "H4": 0.002, "D1": 0.002,
        },
    )


def canonical_symbol(symbol: str) -> str:
    return instrument_for(symbol).key


register_instrument(XAUUSD)
