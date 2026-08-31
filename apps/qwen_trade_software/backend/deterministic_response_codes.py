"""Deterministic response code mapping system for 90%+ accuracy.

This module maps Qwen's natural language responses to standardized, deterministic
response codes based on structural analysis patterns. This eliminates label ambiguity
and ensures consistent mapping across all model versions.

The system uses closed-candle structure analysis to:
1. Validate Qwen's response against actual price action
2. Assign deterministic codes based on structure, not natural language
3. Flag mismatches for monitoring and model improvement
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Optional


class ResponseCode(str, Enum):
    """Standardized response codes based on structural price action.

    All codes are deterministically derived from closed-candle analysis,
    independent of Qwen's natural language description.
    """

    # Rejection responses (price rejected by level)
    SWEEP_REJECTION = "sweep_rejection"          # Price broke level then closed back
    PROBE_REJECTION = "probe_rejection"          # Price probed level, closed inside
    FAILED_BREAK = "failed_break"                # Attempted break, rejection inside
    DOUBLE_REJECTION = "double_rejection"        # Rejected same level twice in sequence

    # Acceptance responses (price accepted through level)
    ACCEPTANCE = "acceptance"                    # Close beyond level (broken)
    STRONG_ACCEPTANCE = "strong_acceptance"      # Acceptance with size/power
    MULTIPLE_acceptance = "multiple_acceptance"  # Multiple closes beyond level

    # Continuation patterns
    CONTINUATION_UP = "continuation_up"          # Uptrend continuation from level
    CONTINUATION_DOWN = "continuation_down"      # Downtrend continuation from level
    RETEST_ACCEPTANCE = "retest_acceptance"      # Retest of broken level, accepted
    RETEST_REJECTION = "retest_rejection"        # Retest of broken level, rejected

    # Reversal patterns
    REVERSAL_BUY = "reversal_buy"               # Sell level with reversal buy setup
    REVERSAL_SELL = "reversal_sell"             # Buy level with reversal sell setup
    DOUBLE_TOP = "double_top"                   # Two closes at same resistance
    DOUBLE_BOTTOM = "double_bottom"             # Two closes at same support

    # Confluence/accumulation
    ACCUMULATION = "accumulation"               # Consolidation, no clear direction
    PRICE_ACTION_BALANCE = "price_action_balance"  # Balanced buyers/sellers
    TEST_AND_HOLD = "test_and_hold"            # Tested level, held above/below

    # Micro/indecision patterns
    INSIDE_DAY = "inside_day"                   # Range inside prior candle
    DOJI_PATTERN = "doji_pattern"               # Open close near equal
    SPINNING_TOP = "spinning_top"               # Small body, long wicks

    # Gap patterns
    GAP_ACCEPTANCE = "gap_acceptance"           # Gap through level
    GAP_REJECTION = "gap_rejection"             # Gap but close back

    # No-action patterns
    NO_RESPONSE = "no_response"                 # No structural action at level
    UNTESTED = "untested"                       # Level not reached in candle
    OUTSIDE_RANGE = "outside_range"             # Candle outside level range


@dataclass(frozen=True)
class StructuralPattern:
    """Describes structural price action against a level."""
    level_id: str
    zone_side: str  # "support" or "resistance"
    zone_low: float
    zone_high: float

    # Candle properties
    candle_open: float
    candle_high: float
    candle_low: float
    candle_close: float

    # Derived metrics
    atr: Optional[float] = None
    point_size: float = 0.0

    def get_response_code(self) -> ResponseCode:
        """Deterministically compute response code from structure.

        This is the core mapping: price structure → response code.
        Independent of Qwen's natural language description.
        """
        lo, hi = self.zone_low, self.zone_high
        o, h, l, c = self.candle_open, self.candle_high, self.candle_low, self.candle_close

        # Expand zone by point size if needed
        if lo == hi:
            half = max(abs(self.point_size), 1e-12)
            lo, hi = lo - half, hi + half

        scale = max(abs(self.atr or 0), hi - lo, abs(self.point_size), 1e-12)
        body = abs(c - o)
        candle_range = max(h - l, 0.0)

        if self.zone_side == "resistance":
            return self._resistance_response(lo, hi, o, h, l, c, body, candle_range, scale)
        else:
            return self._support_response(lo, hi, o, h, l, c, body, candle_range, scale)

    def _resistance_response(
        self, lo, hi, o, h, l, c, body, candle_range, scale
    ) -> ResponseCode:
        """Analyze candle against resistance level."""
        probed = h >= lo
        closed_back = c <= hi
        swept = h > hi and closed_back
        accepted = c > hi

        # Determine body size relative to candle
        body_fraction = body / candle_range if candle_range else 0.0

        # Measure excursion and return
        excursion = max(0.0, h - hi)
        return_distance = max(0.0, hi - c)
        excursion_atr = excursion / scale
        return_atr = return_distance / scale

        # No probe = no response
        if not probed:
            return ResponseCode.UNTESTED

        # Hard acceptance (close clearly above)
        if accepted:
            if body_fraction > 0.75 or candle_range > 1.5 * (hi - lo):
                return ResponseCode.STRONG_ACCEPTANCE
            return ResponseCode.ACCEPTANCE

        # Sweep (broke through then closed back)
        if swept:
            if excursion_atr > 0.5 and return_atr < 0.2:
                return ResponseCode.SWEEP_REJECTION
            elif excursion_atr > 1.0:
                return ResponseCode.DOUBLE_REJECTION  # Strong probe and return
            return ResponseCode.SWEEP_REJECTION

        # Probe only (tested but no break)
        if probed and closed_back:
            if return_atr > 0.3:
                return ResponseCode.TEST_AND_HOLD
            if body_fraction < 0.3:
                return ResponseCode.DOJI_PATTERN
            return ResponseCode.PROBE_REJECTION

        return ResponseCode.NO_RESPONSE

    def _support_response(
        self, lo, hi, o, h, l, c, body, candle_range, scale
    ) -> ResponseCode:
        """Analyze candle against support level."""
        probed = l <= hi
        closed_back = c >= lo
        swept = l < lo and closed_back
        accepted = c < lo

        # Determine body size
        body_fraction = body / candle_range if candle_range else 0.0

        # Measure excursion and return
        excursion = max(0.0, lo - l)
        return_distance = max(0.0, c - lo)
        excursion_atr = excursion / scale
        return_atr = return_distance / scale

        # No probe = no response
        if not probed:
            return ResponseCode.UNTESTED

        # Hard acceptance (close clearly below)
        if accepted:
            if body_fraction > 0.75 or candle_range > 1.5 * (hi - lo):
                return ResponseCode.STRONG_ACCEPTANCE
            return ResponseCode.ACCEPTANCE

        # Sweep (broke through then closed back)
        if swept:
            if excursion_atr > 0.5 and return_atr < 0.2:
                return ResponseCode.SWEEP_REJECTION
            elif excursion_atr > 1.0:
                return ResponseCode.DOUBLE_REJECTION
            return ResponseCode.SWEEP_REJECTION

        # Probe only (tested but no break)
        if probed and closed_back:
            if return_atr > 0.3:
                return ResponseCode.TEST_AND_HOLD
            if body_fraction < 0.3:
                return ResponseCode.DOJI_PATTERN
            return ResponseCode.PROBE_REJECTION

        return ResponseCode.NO_RESPONSE


@dataclass
class ResponseCodeMapping:
    """Maps Qwen response to deterministic code and tracks accuracy."""

    level_id: str
    qwen_response: str  # Natural language from Qwen
    qwen_confidence: int  # Qwen's confidence 0-100
    deterministic_code: ResponseCode  # Computed from structure
    mismatch: bool  # True if Qwen's response doesn't match structure
    match_score: float  # 0.0 to 1.0; how well Qwen response matches structure

    def __post_init__(self):
        """Validate mapping consistency."""
        if self.mismatch and self.match_score > 0.7:
            self.mismatch = False  # Partial match; not a full mismatch


class DeterministicResponseMapper:
    """Maps Qwen responses to deterministic codes with accuracy tracking."""

    def __init__(self):
        self.mappings: list[ResponseCodeMapping] = []
        self.accuracy_by_code: dict[ResponseCode, dict] = {}
        self.total_mappings = 0
        self.mismatches = 0

    def map_response(
        self,
        pattern: StructuralPattern,
        qwen_response: str,
        qwen_confidence: int,
    ) -> ResponseCodeMapping:
        """Map Qwen's response to deterministic code.

        Returns mapping with accuracy metrics.
        """
        deterministic_code = pattern.get_response_code()
        match_score = self._score_match(qwen_response, deterministic_code)
        mismatch = match_score < 0.7

        mapping = ResponseCodeMapping(
            level_id=pattern.level_id,
            qwen_response=qwen_response,
            qwen_confidence=qwen_confidence,
            deterministic_code=deterministic_code,
            mismatch=mismatch,
            match_score=match_score,
        )

        self._track_mapping(mapping)
        return mapping

    def _score_match(self, qwen_response: str, code: ResponseCode) -> float:
        """Score how well Qwen's response matches the deterministic code.

        Returns 0.0-1.0; 1.0 = perfect match, 0.0 = complete mismatch.
        """
        response_lower = qwen_response.lower()

        # Map code to keywords that should appear in response
        keywords_by_code = {
            ResponseCode.SWEEP_REJECTION: ["sweep", "extreme", "rejection"],
            ResponseCode.PROBE_REJECTION: ["probe", "rejection", "inside"],
            ResponseCode.ACCEPTANCE: ["acceptance", "broken", "through"],
            ResponseCode.CONTINUATION_UP: ["continuation", "trending", "up"],
            ResponseCode.CONTINUATION_DOWN: ["continuation", "trending", "down"],
            ResponseCode.REVERSAL_BUY: ["reversal", "buy", "bottom"],
            ResponseCode.REVERSAL_SELL: ["reversal", "sell", "top"],
            ResponseCode.TEST_AND_HOLD: ["test", "hold", "defended"],
            ResponseCode.DOUBLE_REJECTION: ["double", "rejection"],
            ResponseCode.NO_RESPONSE: ["no response", "untested", "no action"],
        }

        target_keywords = keywords_by_code.get(code, [])
        if not target_keywords:
            return 0.5  # Unknown code; moderate confidence

        matches = sum(1 for kw in target_keywords if kw in response_lower)
        match_score = min(1.0, matches / len(target_keywords))

        return match_score

    def _track_mapping(self, mapping: ResponseCodeMapping) -> None:
        """Track mapping for accuracy statistics."""
        self.mappings.append(mapping)
        self.total_mappings += 1
        if mapping.mismatch:
            self.mismatches += 1

        # Initialize code stats if needed
        if mapping.deterministic_code not in self.accuracy_by_code:
            self.accuracy_by_code[mapping.deterministic_code] = {
                "total": 0,
                "accurate": 0,
                "match_scores": [],
            }

        stats = self.accuracy_by_code[mapping.deterministic_code]
        stats["total"] += 1
        stats["match_scores"].append(mapping.match_score)
        if not mapping.mismatch:
            stats["accurate"] += 1

    def accuracy_by_response_code(self) -> dict[ResponseCode, float]:
        """Return accuracy (%) for each response code."""
        result = {}
        for code, stats in self.accuracy_by_code.items():
            if stats["total"] > 0:
                accuracy = (stats["accurate"] / stats["total"]) * 100
                result[code] = accuracy
        return result

    def overall_accuracy(self) -> float:
        """Return overall accuracy (%)."""
        if self.total_mappings == 0:
            return 0.0
        return ((self.total_mappings - self.mismatches) / self.total_mappings) * 100

    def get_mismatches(self, threshold: float = 0.5) -> list[ResponseCodeMapping]:
        """Get mappings where Qwen's response doesn't match structure."""
        return [m for m in self.mappings if m.match_score < threshold]


# Global mapper instance
_GLOBAL_MAPPER = None


def get_mapper() -> DeterministicResponseMapper:
    """Get or create global response mapper."""
    global _GLOBAL_MAPPER
    if _GLOBAL_MAPPER is None:
        _GLOBAL_MAPPER = DeterministicResponseMapper()
    return _GLOBAL_MAPPER


def map_response(
    pattern: StructuralPattern,
    qwen_response: str,
    qwen_confidence: int,
) -> ResponseCodeMapping:
    """Convenience function to map response using global mapper."""
    return get_mapper().map_response(pattern, qwen_response, qwen_confidence)


def get_accuracy_report() -> dict:
    """Get detailed accuracy report."""
    mapper = get_mapper()
    return {
        "overall_accuracy_percent": round(mapper.overall_accuracy(), 2),
        "total_mappings": mapper.total_mappings,
        "mismatches": mapper.mismatches,
        "accuracy_by_code": {
            code.value: round(acc, 2)
            for code, acc in mapper.accuracy_by_response_code().items()
        },
    }
