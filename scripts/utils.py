"""
QuantLLMBot Phase 4 Utility Functions
Helpers for data loading, formatting, metrics, and logging.
"""

import json
import logging
from pathlib import Path
from typing import List, Dict, Any, Tuple, Optional
import numpy as np
from tqdm import tqdm

logger = logging.getLogger(__name__)


# ============================================================================
# JSONL LOADING
# ============================================================================

def load_jsonl(filepath: Path, start_line: int = 0, end_line: Optional[int] = None) -> List[Dict[str, Any]]:
    """
    Load JSONL file with optional line range filtering.

    Args:
        filepath: Path to JSONL file
        start_line: Start line (0-indexed)
        end_line: End line (exclusive, 0-indexed). If None, load to end.

    Returns:
        List of parsed JSON objects
    """
    data = []
    with open(filepath, 'r', encoding='utf-8') as f:
        for idx, line in enumerate(f):
            if end_line is not None and idx >= end_line:
                break
            if idx < start_line:
                continue
            try:
                obj = json.loads(line.strip())
                data.append(obj)
            except json.JSONDecodeError as e:
                logger.warning(f"Failed to parse line {idx} in {filepath}: {e}")

    logger.info(f"Loaded {len(data)} records from {filepath} (lines {start_line}-{end_line or 'end'})")
    return data


def save_jsonl(data: List[Dict[str, Any]], filepath: Path) -> None:
    """Save list of dicts to JSONL file."""
    with open(filepath, 'w', encoding='utf-8') as f:
        for obj in data:
            f.write(json.dumps(obj) + '\n')
    logger.info(f"Saved {len(data)} records to {filepath}")


# ============================================================================
# INSTRUCTION-RESPONSE PAIR FORMATTING
# ============================================================================

def format_principle_context(principles: List[Dict[str, Any]], topic: Optional[str] = None) -> str:
    """
    Create a formatted system prompt from principles.

    Args:
        principles: List of principle dicts from stage_01
        topic: If given, only include principles for this topic. All 35
            principles together are ~6k tokens and overflow the 4096-token
            budget, truncating the response out of the training sequence.

    Returns:
        Formatted principle context string
    """
    if topic is not None:
        subset = [p for p in principles if p.get("topic") == topic]
        if subset:
            principles = subset

    lines = ["# Foundational Principles for Trading Decisions\n"]
    for p in principles:
        lines.append(f"## {p.get('principle_name', 'Unknown')}")
        lines.append(f"Topic: {p.get('topic', 'N/A')}")
        lines.append(f"Core Concept: {p.get('core_concept', 'N/A')}")
        lines.append(f"Foundational Rule: {p.get('foundational_rule', 'N/A')}")
        lines.append(f"Why It Matters: {p.get('why_matters', 'N/A')}")
        lines.append("")

    return "\n".join(lines)


def create_instruction_response_pair(
    example: Dict[str, Any],
    principle_context: str,
    contract: Dict[str, Any]
) -> Dict[str, str]:
    """
    Create a single instruction-response pair from stage_02 example and stage_04 contract.

    Args:
        example: Single record from stage_02
        principle_context: Formatted principles from stage_01
        contract: Single record from stage_04

    Returns:
        Dict with 'instruction' and 'response' keys
    """

    # Instruction: Setup + principles
    instruction = f"""<principle_context>
{principle_context}
</principle_context>

<trade_setup>
Topic: {example.get('topic', 'N/A')}
Title: {example.get('title', 'N/A')}
Setup: {example.get('setup', 'N/A')}
</trade_setup>

Based on the principles above and the trade setup, decide using this contract:
Entry role: Action open|wait|skip; Direction buy|sell|none; Confidence 0-100;
Auction State; Skip Reason Code when skip; Target Mode; Missing Fact when wait;
named Key Levels; Entry/SL/TP when open.
Management role: Management Action hold|protect|close at one decision level.
Session permission and closed-bar acceptance override pattern names."""

    # Bridge toward live qwen_cached_entry + qwen_trade_management.
    role = contract.get("role") or "entry"
    entry = contract.get("entry_price", 0)
    sl = contract.get("sl_price", 0)
    tp = contract.get("tp_price", 0)
    sl_usd = contract.get("sl_usd", 0)
    tp_usd = contract.get("tp_usd", 0)
    key_levels = contract.get("key_levels", "N/A")
    trade_decision = contract.get("trade_decision", "HOLD")
    auction_state = contract.get("auction_state") or "unclear"
    skip_code = contract.get("skip_reason_code")
    target_mode = contract.get("target_mode") or "none"
    missing_fact = contract.get("missing_fact")
    action = contract.get("action")
    direction = contract.get("direction")
    if not action or not direction:
        td = str(trade_decision).lower()
        if td.startswith("skip"):
            action, direction = "skip", "none"
        elif td.startswith("wait"):
            action, direction = "wait", "none"
        elif entry in (0, 0.0, None) and role != "management":
            action, direction = "wait", "none"
        elif "short" in td or "sell" in td:
            action, direction = "open", "sell"
        elif "long" in td or "buy" in td:
            action, direction = "open", "buy"
        else:
            action, direction = "open", "buy"
            if entry and sl and sl > entry:
                direction = "sell"

    conf = contract.get("confidence")
    if conf is None:
        conv = float(contract.get("conviction_score", 0.5) or 0.5)
        conf = int(round(max(0, min(100, conv * 100))))
        if action in ("wait", "skip"):
            conf = min(int(conf), 50)
        elif action == "open" and conf < 51:
            conf = 51

    summary = contract.get("decision_conditions") or trade_decision

    if role == "management":
        mgmt = contract.get("management_action") or "hold"
        thesis = contract.get("thesis_state") or "valid"
        conf_type = contract.get("confirmation_type") or "none"
        d_level = contract.get("decision_level_ref") or "N/A"
        n_target = contract.get("next_target_ref") or "none"
        close_ok = bool(contract.get("close_confirmed"))
        response = f"""Role: management
Management Action: {mgmt}
Direction: {direction}
Thesis State: {thesis}
Confirmation Type: {conf_type}
Decision Level: {d_level}
Next Target: {n_target}
Close Confirmed: {str(close_ok).lower()}
Auction State: {auction_state}
Confidence: {conf}

Key Levels: {key_levels}
Entry: N/A
Stop Loss: N/A
Take Profit: N/A

Evidence: {contract.get('evidence_label', 'Unknown')}

Summary: {summary}

Reasoning: Open-position management. '{contract.get('detector_output', 'neutral')}'
with conditions '{summary}' → management_action={mgmt} (never average/reverse)."""
    else:
        is_no_trade = action in ("wait", "skip") or entry in (0, 0.0, None)
        skip_line = f"Skip Reason Code: {skip_code}" if action == "skip" and skip_code else "Skip Reason Code: none"
        miss_line = f"Missing Fact: {missing_fact}" if action == "wait" and missing_fact else "Missing Fact: none"
        if is_no_trade:
            trade_mgmt = f"""Key Levels: {key_levels}
Entry: N/A
Stop Loss: N/A
Take Profit: N/A
Execution Plan: status={'skip' if action == 'skip' else 'wait'}"""
        else:
            trade_mgmt = f"""Key Levels: {key_levels}
Entry: {entry}
Stop Loss: {sl} (${sl_usd} beyond invalidation)
Take Profit: {tp} (${tp_usd} target)
Execution Plan: status=ready side={direction}"""

        response = f"""Role: entry
Action: {action}
Direction: {direction}
Decision: {trade_decision}
Confidence: {conf}
Auction State: {auction_state}
{skip_line}
Target Mode: {target_mode}
{miss_line}

{trade_mgmt}

Evidence: {contract.get('evidence_label', 'Unknown')}

Conviction Score: {contract.get('conviction_score', 0.5)}

Summary: {summary}

Reasoning: The detector output indicates '{contract.get('detector_output', 'neutral')}'.
Given the conditions '{summary}',
the appropriate trade decision is '{trade_decision}' with risk controls: {contract.get('risk_control', 'None specified')}."""

    return {
        "instruction": instruction.strip(),
        "response": response.strip(),
        "example_id": example.get('example_id'),
        "topic": example.get('topic'),
        "bucket": example.get('bucket')
    }


def prepare_training_data(
    stage_02_data: List[Dict[str, Any]],
    stage_01_data: List[Dict[str, Any]],
    stage_04_data: List[Dict[str, Any]],
    start_idx: int = 0,
    end_idx: Optional[int] = None
) -> List[Dict[str, str]]:
    """
    Combine all three stages into instruction-response pairs.

    Args:
        stage_02_data: Worked examples
        stage_01_data: Principles
        stage_04_data: Decision contracts
        start_idx: Start index (0-based)
        end_idx: End index (exclusive, 0-based)

    Returns:
        List of instruction-response pairs ready for training
    """
    if end_idx is None:
        end_idx = len(stage_02_data)

    training_pairs = []

    for idx in range(start_idx, min(end_idx, len(stage_02_data))):
        example = stage_02_data[idx]
        contract = stage_04_data[idx]

        # Topic-scoped principles keep the prompt inside the 4096-token budget
        principle_context = format_principle_context(stage_01_data, topic=example.get("topic"))
        pair = create_instruction_response_pair(example, principle_context, contract)

        approx_tokens = (len(pair["instruction"]) + len(pair["response"])) // 3
        if approx_tokens > 3800:
            logger.warning(
                f"Example {example.get('example_id')} is ~{approx_tokens} tokens; "
                f"risk of truncating the response at max_seq_length=4096"
            )
        training_pairs.append(pair)

    logger.info(f"Created {len(training_pairs)} instruction-response pairs")
    return training_pairs


# ============================================================================
# METRICS & EVALUATION
# ============================================================================

def compute_exact_match(predicted: str, reference: str) -> bool:
    """Check if predicted decision matches reference exactly."""
    return predicted.strip().lower() == reference.strip().lower()


def compute_conviction_mae(predicted_scores: np.ndarray, reference_scores: np.ndarray) -> float:
    """Mean Absolute Error for conviction scores."""
    return float(np.mean(np.abs(predicted_scores - reference_scores)))


def compute_conviction_rmse(predicted_scores: np.ndarray, reference_scores: np.ndarray) -> float:
    """Root Mean Squared Error for conviction scores."""
    return float(np.sqrt(np.mean((predicted_scores - reference_scores) ** 2)))


def compute_decision_agreement(predicted: List[str], reference: List[str]) -> float:
    """Compute % of decisions that match."""
    matches = sum(1 for p, r in zip(predicted, reference) if compute_exact_match(p, r))
    return matches / len(predicted) * 100 if predicted else 0.0


def extract_conviction_score(response_text: str) -> Optional[float]:
    """
    Extract conviction as 0–1 float.
    Prefers Confidence: 0-100 (live bridge), falls back to Conviction Score.
    """
    try:
        if "Confidence:" in response_text:
            part = response_text.split("Confidence:")[1].split("\n")[0].strip()
            # strip trailing comments
            part = part.split()[0]
            val = float(part)
            if val > 1.0:
                return val / 100.0
            return val
        if "Conviction Score:" in response_text:
            score_part = response_text.split("Conviction Score:")[1].split("\n")[0].strip()
            return float(score_part.split()[0])
    except (ValueError, IndexError):
        pass
    return None


def _field_after(response_text: str, label: str) -> Optional[str]:
    """Extract first line value after 'Label:' without matching longer labels."""
    needle = f"\n{label}:"
    text = "\n" + response_text
    if needle not in text:
        # also allow start-of-string
        if response_text.startswith(f"{label}:"):
            return response_text.split(f"{label}:", 1)[1].split("\n", 1)[0].strip()
        return None
    return text.split(needle, 1)[1].split("\n", 1)[0].strip()


def extract_decision(response_text: str) -> Optional[str]:
    """
    Extract trade decision. Prefer Decision: / Management Action:; else Action+Direction.
    """
    try:
        mgmt = _field_after(response_text, "Management Action")
        if mgmt:
            return mgmt.strip().title()
        decision = _field_after(response_text, "Decision")
        if decision:
            return decision
        action = (_field_after(response_text, "Action") or "").lower()
        direction = (_field_after(response_text, "Direction") or "").lower()
        if action in ("wait", "skip"):
            return "Wait for confirmation" if action == "wait" else "Skip"
        if action == "open" and direction in ("buy", "sell"):
            return "Long scalp" if direction == "buy" else "Short reversal"
    except IndexError:
        pass
    return None


def extract_action_direction(response_text: str) -> tuple:
    """Return (action, direction) from bridge fields if present."""
    mgmt = _field_after(response_text, "Management Action")
    if mgmt:
        direction = (_field_after(response_text, "Direction") or "").lower() or None
        return mgmt.lower(), direction
    action = (_field_after(response_text, "Action") or "").lower() or None
    direction = (_field_after(response_text, "Direction") or "").lower() or None
    return action, direction


def extract_evidence_label(response_text: str) -> Optional[str]:
    """Extract Evidence: strong|moderate|weak (case-insensitive)."""
    raw = _field_after(response_text, "Evidence")
    if not raw:
        return None
    label = raw.split()[0].strip().lower().rstrip(".,;")
    if label in ("strong", "moderate", "weak"):
        return label
    return None


# ============================================================================
# LOGGING SETUP
# ============================================================================

def setup_logging(log_dir: Path, log_name: str = "training.log") -> None:
    """Configure logging to file and console."""
    log_dir.mkdir(parents=True, exist_ok=True)
    log_file = log_dir / log_name

    formatter = logging.Formatter(
        '%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    )

    # File handler
    file_handler = logging.FileHandler(log_file)
    file_handler.setLevel(logging.INFO)
    file_handler.setFormatter(formatter)

    # Console handler
    console_handler = logging.StreamHandler()
    console_handler.setLevel(logging.INFO)
    console_handler.setFormatter(formatter)

    # Root logger
    root_logger = logging.getLogger()
    root_logger.setLevel(logging.INFO)
    root_logger.addHandler(file_handler)
    root_logger.addHandler(console_handler)

    logger.info(f"Logging initialized: {log_file}")


# ============================================================================
# TESTING / DEMO
# ============================================================================

if __name__ == "__main__":
    print("QuantLLMBot Phase 4 Utilities Module")
    print("Functions available:")
    print("  - load_jsonl(filepath, start_line, end_line)")
    print("  - save_jsonl(data, filepath)")
    print("  - format_principle_context(principles)")
    print("  - create_instruction_response_pair(example, principle_context, contract)")
    print("  - prepare_training_data(stage_02, stage_01, stage_04, start_idx, end_idx)")
    print("  - compute_exact_match(predicted, reference)")
    print("  - compute_conviction_mae/rmse(predicted, reference)")
    print("  - compute_decision_agreement(predicted, reference)")
    print("  - extract_conviction_score(response_text)")
    print("  - extract_decision(response_text)")
    print("  - setup_logging(log_dir, log_name)")
