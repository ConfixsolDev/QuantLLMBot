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

def format_principle_context(principles: List[Dict[str, Any]]) -> str:
    """
    Create a formatted system prompt from principles.

    Args:
        principles: List of principle dicts from stage_01

    Returns:
        Formatted principle context string
    """
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

Based on the principles above and the trade setup, what should the trading decision be?"""

    # Response: Decision + evidence + conviction
    response = f"""Decision: {contract.get('trade_decision', 'HOLD')}

Evidence: {contract.get('evidence_label', 'Unknown')}

Conviction Score: {contract.get('conviction_score', 0.5)}

Reasoning: The detector output indicates '{contract.get('detector_output', 'neutral')}'.
Given the conditions '{contract.get('decision_conditions', 'N/A')}',
the appropriate trade decision is '{contract.get('trade_decision', 'HOLD')}' with risk controls: {contract.get('risk_control', 'None specified')}."""

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

    principle_context = format_principle_context(stage_01_data)
    training_pairs = []

    for idx in range(start_idx, min(end_idx, len(stage_02_data))):
        example = stage_02_data[idx]
        contract = stage_04_data[idx]

        pair = create_instruction_response_pair(example, principle_context, contract)
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
    Extract conviction score from model response.
    Looks for "Conviction Score: X.XX" pattern.
    """
    try:
        if "Conviction Score:" in response_text:
            score_part = response_text.split("Conviction Score:")[1].split("\n")[0].strip()
            return float(score_part)
    except (ValueError, IndexError):
        pass
    return None


def extract_decision(response_text: str) -> Optional[str]:
    """
    Extract trade decision from model response.
    Looks for "Decision: XXX" pattern.
    """
    try:
        if "Decision:" in response_text:
            decision = response_text.split("Decision:")[1].split("\n")[0].strip()
            return decision
    except IndexError:
        pass
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
