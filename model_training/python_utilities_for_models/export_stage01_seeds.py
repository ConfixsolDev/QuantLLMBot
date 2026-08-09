#!/usr/bin/env python3
"""
Export the 94 v2 topic seeds to stage-01 JSONL rows.

Input:  _all_seeds.json (from the v2 topic distillation)
Output: stage01_seeds_v003.jsonl (one row per seed, v001/v002-compatible schema)

Handles:
  - Duplicate principle_id fix (second_entry_over_first appears in topic 7 & 9)
  - Citation extraction from lesson text into evidence_sources
  - Clean lesson text (citations stripped) in the assistant message
  - Evidence mapping: evidence_label → evidence_strength
"""
import json, re, sys, hashlib
from pathlib import Path

SEEDS_PATH = Path(sys.argv[1]) if len(sys.argv) > 1 else Path("_all_seeds.json")
OUT_PATH = Path(sys.argv[2]) if len(sys.argv) > 2 else Path("stage01_seeds_v003.jsonl")

SYSTEM_MSG = "Teach compact XAUUSD market-structure principles for later LoRA examples."
SOURCE_POLICY = (
    "Distilled from human doctrine and trading literature principles; "
    "no copied book text."
)

# slug → human-readable topic name for the user message
TOPIC_MAP = {
    "market": "market fundamentals",
    "market_structure": "market structure",
    "candlestick_patterns": "candlestick patterns",
    "timeframe_relations": "timeframe relations",
    "ict_concepts": "ICT concept translation",
    "fvg_imbalance": "FVG and imbalance",
    "trend_trading": "trend trading",
    "range_trading": "range trading",
    "reversal_trading": "reversal trading",
}

# Regex to find inline citations like (slug p.N; slug pp.N-M)
CITE_RE = re.compile(
    r'\s*\('
    r'([a-z][a-z0-9_]*\s+p{1,2}\.\s*[\d,\-\s;a-z_]+)'
    r'\)\s*'
    r'[.;,]?',
    re.IGNORECASE
)

# More precise extraction of individual citations
SINGLE_CITE_RE = re.compile(
    r'([a-z][a-z0-9_]+)\s+(pp?\.\s*[\d,\-]+(?:\s*[\d,\-]+)*)',
    re.IGNORECASE
)


def extract_citations(lesson: str):
    """Return (clean_lesson, list_of_citation_strings)."""
    citations = []
    for m in CITE_RE.finditer(lesson):
        block = m.group(1)
        for cm in SINGLE_CITE_RE.finditer(block):
            slug = cm.group(1)
            pages = cm.group(2)
            citations.append(f"{slug} {pages}")

    # Strip citation parentheticals from the lesson
    clean = CITE_RE.sub(' ', lesson)
    clean = re.sub(r'\s{2,}', ' ', clean).strip()
    # Fix trailing punctuation
    clean = re.sub(r'\s+([.;,])', r'\1', clean)
    return clean, citations


def evidence_basis_from_label(label: str, topic: str, citations: list) -> str:
    """Generate a short evidence_basis string."""
    if label == "strong":
        if citations:
            return "Structurally or definitionally grounded; multiple independent sources."
        return "Definitional or arithmetic — follows from data construction."
    elif label == "moderate":
        return "Established in trading literature but not statistically tested on XAUUSD."
    elif label == "weak":
        return "Single-author assertion or heuristic with known counterexamples."
    elif label == "untested":
        return "Popular practitioner claim with no rigorous test in either direction."
    return "Uncategorised."


def main():
    seeds = json.loads(SEEDS_PATH.read_text())
    seen_ids = {}
    rows = []

    for seed in seeds:
        pid = seed["principle_id"]
        topic = seed["topic"]

        # Fix duplicate IDs
        if pid in seen_ids:
            if topic == "trend_trading":
                pid = "second_entry_with_trend"
            elif topic == "reversal_trading":
                pid = "second_entry_counter_trend"
            else:
                pid = f"{pid}_{topic}"
        seen_ids[pid] = True

        lesson_raw = seed["lesson"]
        practice = seed["practice"]
        guardrail = seed["guardrail"]
        evidence_label = seed["evidence_label"]

        clean_lesson, citations = extract_citations(lesson_raw)
        topic_display = TOPIC_MAP.get(topic, topic.replace("_", " "))

        # Build messages
        user_payload = json.dumps({
            "principle_id": pid,
            "source_policy": SOURCE_POLICY,
            "task": "Learn one market-structure principle before reading chart examples.",
            "topic": topic_display,
        }, sort_keys=True)

        assistant_payload = json.dumps({
            "guardrail": guardrail,
            "lesson": clean_lesson,
            "practice": practice,
            "principle_id": pid,
        }, sort_keys=True)

        messages = [
            {"content": SYSTEM_MSG, "role": "system"},
            {"content": user_payload, "role": "user"},
            {"content": assistant_payload, "role": "assistant"},
        ]

        # Build evidence_sources from citations
        evidence_sources = citations if citations else [f"v2 topic distillation — {topic}"]

        row = {
            "curriculum_stage": "01_principle_foundation",
            "decision_quality_label": "approved_principle",
            "evidence_basis": evidence_basis_from_label(evidence_label, topic, citations),
            "evidence_strength": evidence_label,
            "evidence_sources": evidence_sources,
            "example_id": pid,
            "messages": messages,
            "no_lookahead_confirmed": True,
            "schema_version": 1,
        }
        rows.append(row)

    # Write JSONL
    with open(OUT_PATH, "w") as f:
        for row in rows:
            f.write(json.dumps(row, ensure_ascii=False) + "\n")

    # Summary
    labels = {}
    topics = {}
    for row in rows:
        labels[row["evidence_strength"]] = labels.get(row["evidence_strength"], 0) + 1
        t = json.loads(row["messages"][1]["content"])["topic"]
        topics[t] = topics.get(t, 0) + 1

    print(f"Exported {len(rows)} seeds to {OUT_PATH}")
    print(f"Evidence: {json.dumps(labels, indent=2)}")
    print(f"Topics:   {json.dumps(topics, indent=2)}")

    # Checksum
    content = OUT_PATH.read_bytes()
    print(f"MD5: {hashlib.md5(content).hexdigest()}")
    print(f"Size: {len(content):,} bytes")


if __name__ == "__main__":
    main()
