"""
Code skeleton for multi-timeframe + market structure level detection.
Copy/adapt these as starting points for the implementation modules.
"""

# ============================================================================
# 1. MARKET_STRUCTURE_STRENGTH.PY - Structure Classification
# ============================================================================

from dataclasses import dataclass
from typing import Literal

TimeframeLevel = Literal["M5", "M15", "H1", "H4"]
StructureStrength = Literal["strong", "medium", "weak"]


@dataclass
class StructureStrengthScore:
    """Rate structure quality at one timeframe."""
    timeframe: TimeframeLevel
    strength: StructureStrength
    confidence: float  # 0-100, composited from factors below

    # Components (each 0-100, will be weighted)
    swing_quality: float  # How clean are the swings? (2+ swings = 60, clean = +20)
    fvg_presence: float  # Active unfilled FVG = +30 pts
    order_block_quality: float  # OB with test count: no test=30, 1-2=70, 3+=100
    ote_price_position: float  # Price in OTE zone = 100, near = 60, outside = 20
    liquidity_strength: float  # Pool touch count + proximity (high touch = 100)
    event_recency: float  # Fresh structural event (< 1h) = 80, old = 20


@dataclass
class MultiTimeframeAlignment:
    """Cross-timeframe relationship."""
    primary_tf: TimeframeLevel  # Entry timeframe (typically M5)
    primary_direction: str  # "bullish" or "bearish" at M5

    # Confirmation status
    m15_confirmed: bool  # M15 agrees with M5 direction
    h1_confirmed: bool  # H1 agrees with M5 direction
    h4_context: bool  # H4 direction (for stop placement context)

    # Score
    alignment_score: float  # 0-100: how strong is the cascade?
    cascade_type: Literal["clean_up", "clean_down", "mixed", "conflicted"]
    # clean_up = M5↑ M15↑ H1↑
    # clean_down = M5↓ M15↓ H1↓
    # mixed = M5↑ M15↑ H1= (partial confirmation)
    # conflicted = M5↑ M15↓ (disagreement)

    conflict_tfs: list[TimeframeLevel]  # Which TFs disagree


class StructureStrengthScorer:
    """Main class for scoring and alignment."""

    def __init__(self):
        # Weighting for components
        self.component_weights = {
            "swing_quality": 0.20,
            "fvg_presence": 0.15,
            "order_block_quality": 0.20,
            "ote_price_position": 0.25,
            "liquidity_strength": 0.20,
        }

    def score_timeframe_strength(
        self,
        tf: TimeframeLevel,
        tracker_snap: dict,  # From StructureTracker.snapshot()[tf]
        fvg_data: list[dict],  # Active FVGs at this TF
        ob_data: list[dict],  # Order blocks at this TF
        ote_data: dict,  # OTE zone info at this TF
        liquidity_pools: list[dict],  # Liquidity levels at this TF
        current_price: float,
    ) -> StructureStrengthScore:
        """
        Score structure quality at one timeframe.

        Inputs:
        - tracker_snap: dict with keys "direction", "swings" (list), "last_swing_time"
        - fvg_data: list of {"high", "low", "filled_pct", "active"}
        - ob_data: list of {"high", "low", "tested_count", "direction"}
        - ote_data: {"sweet_spot", "ote_high", "ote_low", "price_in_zone"}
        - liquidity_pools: list of {"price", "type", "touch_count"}
        - current_price: float

        Returns: StructureStrengthScore with all factors scored 0-100
        """

        # 1. Score swing quality
        swings = tracker_snap.get("swings", [])
        swing_quality = self._score_swings(swings, tf)

        # 2. Score FVG presence
        fvg_score = self._score_fvgs(fvg_data, current_price, tf)

        # 3. Score order blocks
        ob_score = self._score_order_blocks(ob_data, current_price, tf)

        # 4. Score OTE position
        ote_score = self._score_ote_position(ote_data, current_price)

        # 5. Score liquidity
        liq_score = self._score_liquidity(liquidity_pools, current_price, tf)

        # Composite confidence
        confidence = (
            swing_quality * self.component_weights["swing_quality"] +
            fvg_score * self.component_weights["fvg_presence"] +
            ob_score * self.component_weights["order_block_quality"] +
            ote_score * self.component_weights["ote_price_position"] +
            liq_score * self.component_weights["liquidity_strength"]
        )

        # Classify strength
        if confidence >= 70:
            strength = "strong"
        elif confidence >= 50:
            strength = "medium"
        else:
            strength = "weak"

        return StructureStrengthScore(
            timeframe=tf,
            strength=strength,
            confidence=round(confidence, 1),
            swing_quality=round(swing_quality, 1),
            fvg_presence=round(fvg_score, 1),
            order_block_quality=round(ob_score, 1),
            ote_price_position=round(ote_score, 1),
            liquidity_strength=round(liq_score, 1),
        )

    def _score_swings(self, swings: list[dict], tf: TimeframeLevel) -> float:
        """
        Score swing quality.

        Base: Need ≥2 swings (impulse + correction) for any credit = 40 pts
        Clean swings (not at exact same level) = +20 pts
        Recent swing (< 2 bars ago) = +20 pts
        Multiple directional changes = +20 pts

        Range: 0-100
        """
        if len(swings) < 2:
            return 20  # Insufficient swings

        score = 40  # Base for 2+ swings

        # Check if swings form clean pattern (not overlapping)
        if len(set(s.get("level") for s in swings[-3:])) >= 2:
            score += 20

        # Check recency
        if swings and swings[-1].get("bar_index", -999) > -2:
            score += 20

        # Multiple direction changes = good structure
        directions = [s.get("direction") for s in swings[-4:]]
        if directions.count("up") >= 2 and directions.count("down") >= 1:
            score += 20

        return min(100, score)

    def _score_fvgs(self, fvgs: list[dict], current_price: float, tf: TimeframeLevel) -> float:
        """
        Score FVG presence.

        No active FVGs = 20 pts
        Active unfilled FVG = +50 pts
        FVG near current price (within 10 pips) = +20 pts
        Multiple FVGs = +10 pts

        Range: 0-100
        """
        if not fvgs:
            return 20

        score = 20
        active_fvgs = [f for f in fvgs if f.get("active", True) and f.get("filled_pct", 0) < 80]

        if active_fvgs:
            score += 50

            # Check if FVG is near price
            for fvg in active_fvgs:
                hi = fvg.get("high", 0)
                lo = fvg.get("low", 0)
                if lo <= current_price <= hi or abs(current_price - hi) < 10 or abs(current_price - lo) < 10:
                    score += 20
                    break

            # Bonus for multiple
            if len(active_fvgs) > 1:
                score += 10

        return min(100, score)

    def _score_order_blocks(self, obs: list[dict], current_price: float, tf: TimeframeLevel) -> float:
        """
        Score order block quality.

        No OBs = 20 pts
        OB present but untested = +30 pts (potential)
        OB with 1-2 tests = +50 pts (proven)
        OB with 3+ tests = +80 pts (strong liquidity)
        OB near price (within 20 pips) = +20 pts

        Range: 0-100
        """
        if not obs:
            return 20

        score = 20
        for ob in obs:
            test_count = ob.get("tested_count", 0)

            if test_count == 0:
                score = max(score, 50)
            elif test_count <= 2:
                score = max(score, 70)
            else:
                score = max(score, 100)

            # Proximity bonus
            ob_hi = ob.get("high", 0)
            ob_lo = ob.get("low", 0)
            if ob_lo <= current_price <= ob_hi:
                score = min(100, score + 20)

        return min(100, score)

    def _score_ote_position(self, ote_data: dict, current_price: float) -> float:
        """
        Score OTE zone position.

        Price in OTE sweet spot = 100 pts
        Price in OTE zone = 80 pts
        Price near OTE = 60 pts
        Price outside OTE = 20 pts

        Range: 0-100
        """
        if not ote_data:
            return 20

        sweet_spot = ote_data.get("sweet_spot")
        ote_hi = ote_data.get("ote_high")
        ote_lo = ote_data.get("ote_low")

        if sweet_spot and abs(current_price - sweet_spot) < 5:
            return 100

        if ote_lo and ote_hi:
            if ote_lo <= current_price <= ote_hi:
                return 80
            elif abs(current_price - ote_hi) < 15 or abs(current_price - ote_lo) < 15:
                return 60

        return 20

    def _score_liquidity(self, pools: list[dict], current_price: float, tf: TimeframeLevel) -> float:
        """
        Score liquidity pool strength.

        No pools = 20 pts
        Pool with 1-2 touches = +40 pts
        Pool with 3-5 touches = +60 pts
        Pool with 6+ touches = +80 pts (strong level)
        Pool within 15 pips of price = +20 pts bonus

        Range: 0-100
        """
        if not pools:
            return 20

        score = 20
        for pool in pools:
            touches = pool.get("touch_count", 1)
            pool_price = pool.get("price", 0)

            if touches >= 6:
                score = max(score, 100)
            elif touches >= 3:
                score = max(score, 80)
            elif touches >= 1:
                score = max(score, 60)

            # Proximity bonus
            if abs(current_price - pool_price) < 15:
                score = min(100, score + 20)

        return min(100, score)

    def align_timeframes(
        self,
        m5_score: StructureStrengthScore,
        m15_score: StructureStrengthScore,
        h1_score: StructureStrengthScore,
        h4_score: StructureStrengthScore,
        m5_direction: str,  # "bullish" or "bearish"
        m15_direction: str,
        h1_direction: str,
        h4_direction: str,
    ) -> MultiTimeframeAlignment:
        """
        Check if timeframes align.

        Rules:
        - M5 provides the entry signal
        - M15 should confirm (or be neutral, not conflicted)
        - H1 confirmation is bonus
        - H4 is structural context for stops

        Returns score 0-100 and cascade type.
        """

        # Determine cascade type
        if m5_direction == m15_direction == h1_direction == "bullish":
            cascade_type = "clean_up"
            alignment_score = 100
        elif m5_direction == m15_direction == h1_direction == "bearish":
            cascade_type = "clean_down"
            alignment_score = 100
        elif m5_direction == m15_direction and m15_direction != h1_direction:
            cascade_type = "mixed"
            alignment_score = 75
        elif m5_direction == m15_direction:
            cascade_type = "mixed"
            alignment_score = 70
        else:
            cascade_type = "conflicted"
            alignment_score = 30

        # Identify conflicts
        conflicts = []
        if m5_direction != m15_direction:
            conflicts.append("M15")
        if m5_direction != h1_direction:
            conflicts.append("H1")

        return MultiTimeframeAlignment(
            primary_tf="M5",
            primary_direction=m5_direction,
            m15_confirmed=(m15_direction == m5_direction),
            h1_confirmed=(h1_direction == m5_direction),
            h4_context=(h4_direction == m5_direction),
            alignment_score=alignment_score,
            cascade_type=cascade_type,
            conflict_tfs=conflicts,
        )


# ============================================================================
# 2. SESSION_CONTEXT.PY - Time-of-Day Filtering
# ============================================================================

from dataclasses import dataclass
from datetime import datetime
from typing import Literal
import pytz

SessionType = Literal[
    "asian_morning",
    "london_open",
    "london_close",
    "us_morning",
    "us_afternoon",
    "us_close",
    "overnight",
]


@dataclass
class CandlePosition:
    """Where in the current candle are we?"""
    bar_age_seconds: float  # Elapsed since bar open
    bar_duration_seconds: float  # Total bar length
    pct_through_bar: float  # 0.0-1.0
    is_young: bool  # < 20% through
    is_old: bool  # > 80% through


@dataclass
class SessionContext:
    utc_time: datetime
    session_type: SessionType
    seconds_to_session_end: float
    candle_pos: CandlePosition
    session_quality_multiplier: float  # 0.0-1.2


class SessionContextBuilder:
    """Build session context from current time."""

    def __init__(self, broker_timezone: str = "UTC"):
        """
        broker_timezone: "UTC", "Europe/London", "America/New_York", etc.
        """
        self.broker_tz = pytz.timezone(broker_timezone)

    def build(
        self,
        utc_now: datetime,
        current_bar_open_time: datetime,
        bar_duration_seconds: int,  # 60 for M1, 300 for M5, etc.
    ) -> SessionContext:
        """Build session context."""

        broker_time = utc_now.astimezone(self.broker_tz)

        # Determine session
        hour = broker_time.hour
        session_type = self._get_session_type(hour)

        # Time to session end
        seconds_to_end = self._seconds_to_session_end(broker_time, session_type)

        # Candle position
        candle_age = (utc_now - current_bar_open_time).total_seconds()
        pct_through = min(1.0, max(0.0, candle_age / bar_duration_seconds))

        candle_pos = CandlePosition(
            bar_age_seconds=candle_age,
            bar_duration_seconds=bar_duration_seconds,
            pct_through_bar=pct_through,
            is_young=(pct_through < 0.2),
            is_old=(pct_through > 0.8),
        )

        # Session quality multiplier
        quality = self._session_quality_multiplier(session_type, pct_through)

        return SessionContext(
            utc_time=utc_now,
            session_type=session_type,
            seconds_to_session_end=seconds_to_end,
            candle_pos=candle_pos,
            session_quality_multiplier=quality,
        )

    def _get_session_type(self, broker_hour: int) -> SessionType:
        """Determine session from hour (broker timezone)."""
        # Adjust these based on your broker's timezone
        if 0 <= broker_hour < 8:
            return "overnight"
        elif 8 <= broker_hour < 12:
            return "london_open"
        elif 12 <= broker_hour < 16:
            return "london_close"
        elif 16 <= broker_hour < 20:
            return "us_morning"
        elif 20 <= broker_hour < 22:
            return "us_afternoon"
        else:
            return "overnight"

    def _seconds_to_session_end(self, broker_time: datetime, session: SessionType) -> float:
        """Calculate seconds until session ends."""
        hour = broker_time.hour
        minute = broker_time.minute
        second = broker_time.second

        current_seconds = hour * 3600 + minute * 60 + second

        session_end_times = {
            "overnight": 8 * 3600,  # 08:00
            "london_open": 12 * 3600,
            "london_close": 16 * 3600 + 30 * 60,  # 16:30
            "us_morning": 20 * 3600,
            "us_afternoon": 22 * 3600,
        }

        end_time = session_end_times.get(session, 22 * 3600)
        seconds_left = max(0, end_time - current_seconds)

        return seconds_left

    def _session_quality_multiplier(self, session: SessionType, pct_through_bar: float) -> float:
        """
        Return confidence multiplier for this session.

        Base rules:
        - london_open (8-12) = 1.0 (normal, good liquidity)
        - us_morning (16-20) = 1.0
        - london_close (12-16:30) = 0.95 (slightly lower)
        - us_afternoon (20-22) = 0.85 (lower volume)
        - overnight = 0.0 (blocked)
        - young candle (< 20%) = base * 1.05 (early entry is good)
        - old candle (> 80%) = base * 0.90 (late entry is risky)
        """

        base = {
            "london_open": 1.0,
            "london_close": 0.95,
            "us_morning": 1.0,
            "us_afternoon": 0.85,
            "asian_morning": 0.70,
            "overnight": 0.0,
        }[session]

        # Candle timing adjustment
        if pct_through_bar < 0.2:
            base *= 1.05  # Reward early entry
        elif pct_through_bar > 0.8:
            base *= 0.90  # Penalize late entry

        return base


# ============================================================================
# Usage Example in market_structure.py
# ============================================================================

def example_integration():
    """
    How to use these in market_structure.py's _compute_impl():

    # After building candle_data and structure snapshots:

    strength_scorer = StructureStrengthScorer()

    # Score each timeframe
    m5_score = strength_scorer.score_timeframe_strength(
        "M5",
        tracker_snap["M5"],
        fvg_detector.get_fvgs("M5"),
        ob_detector.get_blocks("M5"),
        ote_calculator.get_ote("M5"),
        liquidity_map.get_pools("M5"),
        current_price
    )

    # Similar for M15, H1, H4...

    # Check alignment
    alignment = strength_scorer.align_timeframes(
        m5_score, m15_score, h1_score, h4_score,
        tracker.trend_for("M5"),
        tracker.trend_for("M15"),
        tracker.trend_for("H1"),
        tracker.trend_for("H4"),
    )

    # Build session context
    session_builder = SessionContextBuilder(broker_timezone="UTC")
    session_ctx = session_builder.build(
        utc_now=datetime.utcnow(),
        current_bar_open_time=candle_data["M5"][-1]["time"],
        bar_duration_seconds=300,  # M5
    )

    # Use in entry_policy.py:
    # policy_result = apply_session_filter(policy_decision, session_ctx, alignment)
    """
    pass

