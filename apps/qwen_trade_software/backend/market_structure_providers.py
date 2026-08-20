"""Optional market-structure providers with one pair-agnostic result schema.

External libraries are evidence generators, never live execution authorities.
Every import is optional so a missing/broken research package cannot interrupt
the MT5 cycle.  Providers marked offline_only may repaint, use future bars, or
be too expensive for the 30-second decision path.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from importlib.metadata import PackageNotFoundError, version
from importlib.util import find_spec
from contextlib import redirect_stdout
from io import StringIO
from math import isfinite
from statistics import median
from time import perf_counter
from typing import Any, Protocol


@dataclass(frozen=True, slots=True)
class StructureEvent:
    provider: str
    kind: str
    direction: str
    timeframe: str
    bar_index: int | None = None
    price: float | None = None
    confidence: float = 0.5
    repaint_risk: bool = False
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class ProviderResult:
    provider: str
    available: bool
    status: str
    events: tuple[StructureEvent, ...] = ()
    offline_only: bool = False
    error: str | None = None

    def compact(self) -> dict:
        return {
            "provider": self.provider,
            "available": self.available,
            "status": self.status,
            "offline_only": self.offline_only,
            "events": [asdict(event) for event in self.events],
            **({"error": self.error} if self.error else {}),
        }


class StructureProvider(Protocol):
    name: str
    package: str
    offline_only: bool

    def detect(self, bars: list[dict], timeframe: str, atr: float) -> ProviderResult: ...


def _module_available(module: str) -> bool:
    try:
        return find_spec(module) is not None
    except (ImportError, ModuleNotFoundError, ValueError):
        return False


def _distribution_version(name: str) -> str | None:
    try:
        return version(name)
    except PackageNotFoundError:
        return None


def _prices(bars: list[dict], key: str) -> list[float]:
    values = [float(bar[key]) for bar in bars]
    if not all(isfinite(value) for value in values):
        raise ValueError(f"non-finite {key} value")
    return values


class OptionalProvider:
    name = "optional"
    package = ""
    distribution = ""
    offline_only = False

    def unavailable(self) -> ProviderResult:
        return ProviderResult(self.name, False, "package_missing", offline_only=self.offline_only)

    def failed(self, exc: Exception) -> ProviderResult:
        return ProviderResult(
            self.name, True, "provider_error", offline_only=self.offline_only,
            error=f"{type(exc).__name__}:{exc}",
        )


class ScipySwingProvider(OptionalProvider):
    name, package = "scipy_peaks", "scipy"
    distribution = "scipy"

    def detect(self, bars: list[dict], timeframe: str, atr: float) -> ProviderResult:
        if not _module_available("scipy"):
            return self.unavailable()
        try:
            from scipy.signal import find_peaks
            prominence = max(float(atr) * 0.35, 1e-12)
            highs, lows = _prices(bars, "high"), _prices(bars, "low")
            hi_idx, hi_props = find_peaks(highs, prominence=prominence, distance=2)
            lo_idx, lo_props = find_peaks([-value for value in lows], prominence=prominence, distance=2)
            events = []
            for idx, prom in zip(hi_idx[-6:], hi_props["prominences"][-6:]):
                events.append(StructureEvent(self.name, "swing_high", "bearish", timeframe,
                    int(idx), highs[int(idx)], min(1.0, float(prom) / max(atr, 1e-12))))
            for idx, prom in zip(lo_idx[-6:], lo_props["prominences"][-6:]):
                events.append(StructureEvent(self.name, "swing_low", "bullish", timeframe,
                    int(idx), lows[int(idx)], min(1.0, float(prom) / max(atr, 1e-12))))
            return ProviderResult(self.name, True, "ok", tuple(sorted(events, key=lambda e: e.bar_index or 0)))
        except Exception as exc:
            return self.failed(exc)


class SklearnZoneProvider(OptionalProvider):
    name, package = "sklearn_dbscan", "sklearn"
    distribution = "scikit-learn"

    def detect(self, bars: list[dict], timeframe: str, atr: float) -> ProviderResult:
        if not _module_available("sklearn"):
            return self.unavailable()
        try:
            from sklearn.cluster import DBSCAN
            points = [(i, float(bar[side]), side) for i, bar in enumerate(bars)
                      for side in ("high", "low")]
            scale = max(float(atr), 1e-12)
            labels = DBSCAN(eps=0.25, min_samples=2).fit_predict(
                [[price / scale] for _, price, _ in points]
            )
            events = []
            for label in sorted(set(int(x) for x in labels if int(x) >= 0)):
                members = [points[i] for i, value in enumerate(labels) if int(value) == label]
                price = median(item[1] for item in members)
                highs = sum(item[2] == "high" for item in members)
                direction = "bearish" if highs >= len(members) / 2 else "bullish"
                events.append(StructureEvent(self.name, "resistance_zone" if direction == "bearish"
                    else "support_zone", direction, timeframe, max(item[0] for item in members), price,
                    min(1.0, len(members) / 5), metadata={"touches": len(members), "eps_atr": 0.25}))
            return ProviderResult(self.name, True, "ok", tuple(events[-8:]))
        except Exception as exc:
            return self.failed(exc)


class TALibProvider(OptionalProvider):
    name, package = "talib_patterns", "talib"
    distribution = "TA-Lib"

    def detect(self, bars: list[dict], timeframe: str, atr: float) -> ProviderResult:
        if not _module_available("talib"):
            return self.unavailable()
        try:
            import numpy as np
            import talib
            o, h, low, c = (np.asarray(_prices(bars, key), dtype=float)
                            for key in ("open", "high", "low", "close"))
            patterns = {
                "engulfing": talib.CDLENGULFING(o, h, low, c),
                "hammer": talib.CDLHAMMER(o, h, low, c),
                "shooting_star": talib.CDLSHOOTINGSTAR(o, h, low, c),
            }
            events = []
            for kind, values in patterns.items():
                for idx in np.flatnonzero(values)[-3:]:
                    value = int(values[idx])
                    events.append(StructureEvent(self.name, kind,
                        "bullish" if value > 0 else "bearish", timeframe, int(idx), float(c[idx]),
                        min(1.0, abs(value) / 100)))
            return ProviderResult(self.name, True, "ok", tuple(events))
        except Exception as exc:
            return self.failed(exc)


class SmartMoneyConceptsProvider(OptionalProvider):
    name, package = "smartmoneyconcepts", "smartmoneyconcepts"
    distribution = "smartmoneyconcepts"

    def detect(self, bars: list[dict], timeframe: str, atr: float) -> ProviderResult:
        if not _module_available("smartmoneyconcepts"):
            return self.unavailable()
        try:
            import pandas as pd
            # The package prints a Unicode banner at import time.  Capture it
            # so Windows console encoding cannot turn a valid provider into an
            # import failure and so the research worker stays machine-readable.
            with redirect_stdout(StringIO()):
                from smartmoneyconcepts import smc
            frame = pd.DataFrame(bars).rename(columns=str.lower)
            swings = smc.swing_highs_lows(frame, swing_length=3)
            events = []
            for idx, row in swings.dropna(subset=["HighLow"]).tail(8).iterrows():
                bullish = float(row["HighLow"]) < 0
                events.append(StructureEvent(self.name, "swing_low" if bullish else "swing_high",
                    "bullish" if bullish else "bearish", timeframe, int(idx), float(row["Level"]),
                    0.6, repaint_risk=True, metadata={"centered_window": 3}))
            return ProviderResult(self.name, True, "ok", tuple(events))
        except Exception as exc:
            return self.failed(exc)


class CapabilityProvider(OptionalProvider):
    """Register research packages whose outputs belong in replay, not live bars."""

    def __init__(self, name: str, package: str, *, distribution_name: str | None = None,
                 repaint_risk: bool = False):
        self.name, self.package, self.offline_only = name, package, True
        self.distribution = distribution_name or package
        self.repaint_risk = repaint_risk

    def detect(self, bars: list[dict], timeframe: str, atr: float) -> ProviderResult:
        available = _module_available(self.package)
        return ProviderResult(self.name, available,
            "offline_only" if available else "package_missing", offline_only=True)


def default_providers() -> tuple[StructureProvider, ...]:
    return (
        ScipySwingProvider(), SklearnZoneProvider(), TALibProvider(),
        SmartMoneyConceptsProvider(),
        CapabilityProvider("smc_toolkit", "smc_toolkit", distribution_name="smc-toolkit"),
        CapabilityProvider("ruptures_changepoints", "ruptures"),
        CapabilityProvider("statsmodels_markov", "statsmodels"),
        CapabilityProvider("vectorbt_replay", "vectorbt"),
        CapabilityProvider("stock_indicators_zigzag", "stock_indicators", repaint_risk=True),
    )


def run_shadow_providers(
    bars: list[dict], timeframe: str, atr: float,
    providers: tuple[StructureProvider, ...] | None = None,
) -> dict:
    """Run only live-safe providers and return bounded diagnostic consensus."""
    results = []
    latencies_ms: dict[str, float] = {}
    for provider in providers or default_providers():
        if provider.offline_only:
            continue
        started = perf_counter()
        result = provider.detect(bars, timeframe, atr)
        latencies_ms[provider.name] = round((perf_counter() - started) * 1000, 3)
        results.append(result)
    events = [event for result in results for event in result.events]
    bullish = sum(event.direction == "bullish" for event in events)
    bearish = sum(event.direction == "bearish" for event in events)
    denominator = bullish + bearish
    provider_decisions = []
    for result in results:
        provider_bullish = sum(event.direction == "bullish" for event in result.events)
        provider_bearish = sum(event.direction == "bearish" for event in result.events)
        provider_total = provider_bullish + provider_bearish
        direction = (
            "bullish" if provider_bullish > provider_bearish else
            "bearish" if provider_bearish > provider_bullish else "mixed"
        )
        provider_decisions.append({
            "provider": result.provider,
            "status": result.status,
            "direction": direction,
            "agreement": round(max(provider_bullish, provider_bearish) / provider_total, 3)
            if provider_total else 0.0,
            "event_count": provider_total,
            "latency_ms": latencies_ms.get(result.provider),
            "error": result.error,
        })
    providers_ok = [r.provider for r in results if r.status == "ok"]
    providers_missing = [r.provider for r in results if not r.available]
    provider_errors = [r.provider for r in results if r.status == "provider_error"]
    return {
        "mode": "shadow_only",
        "status": "ok" if providers_ok else "no_providers_available",
        "direction": "bullish" if bullish > bearish else "bearish" if bearish > bullish else "mixed",
        "agreement": round(max(bullish, bearish) / denominator, 3) if denominator else 0.0,
        "event_count": denominator,
        "providers_ok": providers_ok,
        "providers_missing": providers_missing,
        "provider_errors": provider_errors,
        "provider_decisions": provider_decisions,
        "execution_authority": False,
    }


def provider_inventory(providers: tuple[StructureProvider, ...] | None = None) -> list[dict]:
    inventory = []
    for provider in providers or default_providers():
        distribution_name = getattr(provider, "distribution", provider.package) or provider.package
        installed_version = _distribution_version(distribution_name)
        inventory.append({
            "provider": provider.name,
            "package": distribution_name,
            "version": installed_version,
            "installed": installed_version is not None,
            "importable": _module_available(provider.package),
            "available": installed_version is not None and _module_available(provider.package),
            "offline_only": provider.offline_only,
            "execution_authority": False,
        })
    return inventory
