#!/bin/bash
# Quick monitoring script for 2026-08-26
# Run this every hour to track volume and quality

LOG_DIR="/sessions/serene-amazing-cori/mnt/QuantLLMBot/apps/qwen_trade_software/backend/logs"
TODAY_LOG="$LOG_DIR/reviews-2026-08-26.jsonl"

echo "════════════════════════════════════════════════════════════════"
echo "TRADING VOLUME & QUALITY MONITOR — $(date)"
echo "════════════════════════════════════════════════════════════════"

if [ ! -f "$TODAY_LOG" ]; then
  echo "⚠️  No log file yet: $TODAY_LOG"
  echo "   Waiting for first proposal..."
  exit 0
fi

echo ""
echo "1️⃣  OVERALL VOLUME"
echo "───────────────────────────────────────────────────────────────"
READY_COUNT=$(grep -c '"status":"ready"' "$TODAY_LOG" 2>/dev/null || echo "0")
WAIT_COUNT=$(grep -c '"status":"wait"' "$TODAY_LOG" 2>/dev/null || echo "0")
echo "   Ready (executable): $READY_COUNT"
echo "   Wait (rejected):    $WAIT_COUNT"
TOTAL=$((READY_COUNT + WAIT_COUNT))
if [ $TOTAL -gt 0 ]; then
  READY_PCT=$((READY_COUNT * 100 / TOTAL))
  echo "   Pass rate: $READY_PCT%"
fi

echo ""
echo "2️⃣  CONFIDENCE DISTRIBUTION (Ready Proposals)"
echo "───────────────────────────────────────────────────────────────"
grep '"status":"ready"' "$TODAY_LOG" 2>/dev/null | \
  grep '"confidence":' | \
  sed 's/.*"confidence":\([0-9]*\).*/\1/' | \
  awk 'BEGIN {min=999; max=0}
       {sum+=$1; count++; if ($1<min) min=$1; if ($1>max) max=$1}
       END {
         printf "   Count: %d\n", count
         printf "   Range: %d to %d\n", min, max
         printf "   Average: %.1f\n", sum/count
       }'

echo ""
echo "3️⃣  TOP 5 REJECTION REASONS (Wait Decisions)"
echo "───────────────────────────────────────────────────────────────"
grep '"reason_code":"' "$TODAY_LOG" 2>/dev/null | \
  sed 's/.*"reason_code":"\([^"]*\)".*/\1/' | \
  sort | uniq -c | sort -rn | head -5 | \
  awk '{printf "   %s: %d\n", $2, $1}'

echo ""
echo "4️⃣  SIDE BALANCE (Buy vs Sell)"
echo "───────────────────────────────────────────────────────────────"
BUY=$(grep '"side":"buy"' "$TODAY_LOG" 2>/dev/null | wc -l)
SELL=$(grep '"side":"sell"' "$TODAY_LOG" 2>/dev/null | wc -l)
echo "   Buy:  $BUY"
echo "   Sell: $SELL"
if [ $((BUY + SELL)) -gt 0 ]; then
  BUY_PCT=$((BUY * 100 / (BUY + SELL)))
  echo "   Buy ratio: $BUY_PCT%"
fi

echo ""
echo "5️⃣  SYMMETRY THROTTLING STATUS"
echo "───────────────────────────────────────────────────────────────"
THROTTLED=$(grep -c '"reason_code":"side:symmetry_throttled"' "$TODAY_LOG" 2>/dev/null || echo "0")
echo "   Symmetry throttled: $THROTTLED"
if [ $THROTTLED -gt 5 ]; then
  echo "   ⚠️  High throttling — one-sided day?"
else
  echo "   ✅ Normal throttling"
fi

echo ""
echo "6️⃣  STRUCTURAL FILTERS (Invariant Checks)"
echo "───────────────────────────────────────────────────────────────"
TIMEFRAME=$(grep -c '"reason_code":"side:timeframe_incoherent"' "$TODAY_LOG" 2>/dev/null || echo "0")
INVALIDATION=$(grep -c '"reason_code":"side:invalidation_incoherent"' "$TODAY_LOG" 2>/dev/null || echo "0")
BLOCKING=$(grep -c '"reason_code":"side:blocking_trap"' "$TODAY_LOG" 2>/dev/null || echo "0")
echo "   Timeframe rejected: $TIMEFRAME"
echo "   Invalidation gap:   $INVALIDATION"
echo "   Blocking traps:     $BLOCKING"

echo ""
echo "════════════════════════════════════════════════════════════════"
echo "TARGET: ≥ 50 ready proposals by end of day"
echo "CURRENT: $READY_COUNT ready"

if [ $READY_COUNT -ge 50 ]; then
  echo "✅ TARGET MET — Keep monitoring for quality"
else
  REMAINING=$((50 - READY_COUNT))
  echo "⏳ Need $REMAINING more to reach target"
fi

echo "════════════════════════════════════════════════════════════════"
