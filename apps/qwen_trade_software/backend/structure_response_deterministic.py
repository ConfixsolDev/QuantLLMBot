"""Integration of deterministic response codes into existing structure analysis.

This module wraps evaluate_zone_response() to add deterministic code mapping
and accuracy tracking without changing the existing API.
"""

from __future__ import annotations

import logging
from typing import Optional

from deterministic_response_codes import (
    DeterministicResponseMapper,
    ResponseCode,
    ResponseCodeMapping,
    StructuralPattern,
)
from structure_response import evaluate_zone_response


logger = logging.getLogger(__name__)


class DeterministicStructureResponse:
    """Wraps structure_response.evaluate_zone_response with deterministic codes."""

    def __init__(self):
        self.mapper = DeterministicResponseMapper()
        self.accuracy_threshold = 0.90  # 90% is the target

    def evaluate_with_code(
        self,
        level: dict,
        closed_candle: dict,
        *,
        atr: Optional[float] = None,
        point_size: float = 0.0,
        qwen_response: Optional[str] = None,
        qwen_confidence: int = 50,
    ) -> dict | None:
        """Evaluate zone response and add deterministic code mapping.

        Args:
            level: Mapped level with id, side, zone range
            closed_candle: Completed candle OHLC
            atr: Optional ATR for scaling
            point_size: Minimum trade point size
            qwen_response: Optional Qwen's natural language response
            qwen_confidence: Qwen's confidence 0-100

        Returns:
            Original response dict + deterministic_code and mapping fields
        """
        # Get original structural response
        response = evaluate_zone_response(
            level, closed_candle, atr=atr, point_size=point_size
        )
        if response is None:
            return None

        # Extract pattern from inputs
        pattern = StructuralPattern(
            level_id=level.get("id") or level.get("level_id", "unknown"),
            zone_side=response.get("zone_side", "unknown"),
            zone_low=response.get("zone_low", 0.0),
            zone_high=response.get("zone_high", 0.0),
            candle_open=closed_candle.get("open", 0.0),
            candle_high=closed_candle.get("high", 0.0),
            candle_low=closed_candle.get("low", 0.0),
            candle_close=closed_candle.get("close", 0.0),
            atr=atr,
            point_size=point_size,
        )

        # Compute deterministic code
        deterministic_code = pattern.get_response_code()

        # Map Qwen's response if provided
        mapping = None
        match_score = 1.0
        mismatch = False

        if qwen_response:
            mapping = self.mapper.map_response(pattern, qwen_response, qwen_confidence)
            match_score = mapping.match_score
            mismatch = mapping.mismatch

        # Add deterministic fields to response
        response["deterministic_code"] = deterministic_code.value
        response["match_score"] = round(match_score, 4)
        response["mismatch"] = mismatch

        if mapping:
            response["response_mapping"] = {
                "qwen_response": qwen_response,
                "qwen_confidence": qwen_confidence,
                "deterministic_code": deterministic_code.value,
                "match_score": match_score,
                "mismatch": mismatch,
            }

        # Log mismatches for monitoring
        if mismatch:
            logger.warning(
                "Response mismatch for %s: Qwen='%s' (conf=%d) → %s (match=%.2f)",
                level.get("id"),
                qwen_response[:50] if qwen_response else "N/A",
                qwen_confidence,
                deterministic_code.value,
                match_score,
            )

        return response

    def get_accuracy_report(self) -> dict:
        """Get detailed accuracy report for monitoring."""
        overall_acc = self.mapper.overall_accuracy()
        report = {
            "overall_accuracy_percent": round(overall_acc, 2),
            "target_accuracy_percent": round(self.accuracy_threshold * 100, 2),
            "on_target": overall_acc >= (self.accuracy_threshold * 100),
            "total_mappings": self.mapper.total_mappings,
            "mismatches": self.mapper.mismatches,
            "accuracy_by_code": {
                code.value: round(acc, 2)
                for code, acc in self.mapper.accuracy_by_response_code().items()
            },
        }
        return report

    def get_mismatches(self, limit: int = 20) -> list[dict]:
        """Get recent mismatches for debugging."""
        mismatches = self.mapper.get_mismatches(threshold=0.7)
        return [
            {
                "level_id": m.level_id,
                "qwen_response": m.qwen_response[:80],
                "qwen_confidence": m.qwen_confidence,
                "deterministic_code": m.deterministic_code.value,
                "match_score": round(m.match_score, 4),
            }
            for m in mismatches[-limit:]
        ]


# Global instance
_INSTANCE = None


def get_handler() -> DeterministicStructureResponse:
    """Get or create global handler."""
    global _INSTANCE
    if _INSTANCE is None:
        _INSTANCE = DeterministicStructureResponse()
    return _INSTANCE


def evaluate_with_deterministic_code(
    level: dict,
    closed_candle: dict,
    *,
    atr: Optional[float] = None,
    point_size: float = 0.0,
    qwen_response: Optional[str] = None,
    qwen_confidence: int = 50,
) -> dict | None:
    """Convenience function using global handler."""
    return get_handler().evaluate_with_code(
        level,
        closed_candle,
        atr=atr,
        point_size=point_size,
        qwen_response=qwen_response,
        qwen_confidence=qwen_confidence,
    )


def log_accuracy_report() -> None:
    """Log current accuracy report."""
    handler = get_handler()
    report = handler.get_accuracy_report()
    logger.info(
        "Response Code Accuracy: %.1f%% (target: %.1f%%) — %d mappings, %d mismatches",
        report["overall_accuracy_percent"],
        report["target_accuracy_percent"],
        report["total_mappings"],
        report["mismatches"],
    )
    for code, acc in report["accuracy_by_code"].items():
        logger.debug("  %s: %.1f%%", code, acc)
