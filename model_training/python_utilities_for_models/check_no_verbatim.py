#!/usr/bin/env python3
"""
check_no_verbatim.py — Verify no verbatim book text leaked into distilled files.

Extracts n-grams from the source corpus and checks distilled output files
for overlapping sequences. Default n=12 catches virtually all accidental
copying; n=11 catches standard technical phrases that may be false positives.

Usage:
    python check_no_verbatim.py \
        --corpus-dir knowledge/_pdf_extract \
        --check-files knowledge/topics/*.md \
        --n 12

    # Stricter pass (expect some false positives on standard terms):
    python check_no_verbatim.py \
        --corpus-dir knowledge/_pdf_extract \
        --check-files knowledge/topics/*.md \
        --n 11 --show-context
"""
import argparse, re, sys
from pathlib import Path
from collections import defaultdict


def normalize(text: str) -> list[str]:
    """Lowercase, strip punctuation, split into words."""
    text = re.sub(r'[\[\](){}<>]', ' ', text)
    text = re.sub(r'[^\w\s]', '', text.lower())
    return text.split()


def ngrams(words: list[str], n: int):
    """Yield (ngram_tuple, start_index) pairs."""
    for i in range(len(words) - n + 1):
        yield tuple(words[i:i + n]), i


def build_corpus_index(corpus_dir: Path, n: int) -> dict:
    """Build a set of n-grams from all corpus .txt files."""
    index = set()
    file_count = 0
    for f in sorted(corpus_dir.glob("*.txt")):
        words = normalize(f.read_text(encoding="utf-8", errors="replace"))
        for gram, _ in ngrams(words, n):
            index.add(gram)
        file_count += 1
    return index, file_count


def check_file(path: Path, corpus_index: set, n: int, show_context: bool) -> list[dict]:
    """Check a single file against the corpus index."""
    text = path.read_text(encoding="utf-8", errors="replace")
    words = normalize(text)
    hits = []

    for gram, idx in ngrams(words, n):
        if gram in corpus_index:
            context = " ".join(words[max(0, idx - 3):idx + n + 3])
            hit = {
                "file": str(path),
                "position": idx,
                "ngram": " ".join(gram),
                "context": context,
            }
            hits.append(hit)

    # Deduplicate overlapping hits
    if not hits:
        return []

    merged = [hits[0]]
    for h in hits[1:]:
        if h["position"] <= merged[-1]["position"] + n:
            # Extend the previous hit
            if len(h["ngram"]) > len(merged[-1]["ngram"]):
                merged[-1] = h
        else:
            merged.append(h)

    return merged


def main():
    parser = argparse.ArgumentParser(description="Check for verbatim overlap with source corpus")
    parser.add_argument("--corpus-dir", required=True, help="Directory with corpus .txt files")
    parser.add_argument("--check-files", required=True, nargs="+", help="Files to check for overlap")
    parser.add_argument("--n", type=int, default=12, help="N-gram size (default 12)")
    parser.add_argument("--show-context", action="store_true", help="Show surrounding words")
    args = parser.parse_args()

    corpus_dir = Path(args.corpus_dir)
    if not corpus_dir.exists():
        print(f"Error: corpus directory not found: {corpus_dir}", file=sys.stderr)
        return 1

    print(f"Building {args.n}-gram index from {corpus_dir}...")
    corpus_index, file_count = build_corpus_index(corpus_dir, args.n)
    print(f"  {file_count} corpus files, {len(corpus_index):,} unique {args.n}-grams")

    total_hits = 0
    check_paths = []
    for pattern in args.check_files:
        p = Path(pattern)
        if p.exists():
            check_paths.append(p)
        else:
            # Try glob
            check_paths.extend(Path(".").glob(pattern))

    for path in sorted(check_paths):
        hits = check_file(path, corpus_index, args.n, args.show_context)
        if hits:
            print(f"\n{path}: {len(hits)} overlap(s)")
            for h in hits:
                if args.show_context:
                    print(f"  pos {h['position']}: ...{h['context']}...")
                else:
                    print(f"  pos {h['position']}: {h['ngram']}")
            total_hits += len(hits)
        else:
            print(f"  {path}: clean")

    print(f"\nTotal: {total_hits} overlaps at n={args.n}")
    if total_hits > 0 and args.n >= 12:
        print("ACTION REQUIRED: Rewrite overlapping passages in your own words.")
        return 1
    elif total_hits > 0:
        print("Review needed: some hits at n<12 may be standard technical vocabulary.")
        return 0
    else:
        print("No verbatim overlap detected.")
        return 0


if __name__ == "__main__":
    sys.exit(main())
