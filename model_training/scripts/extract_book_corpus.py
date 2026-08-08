#!/usr/bin/env python3
"""
extract_book_corpus.py — Reproduce the full-text corpus from Trading Books PDFs.

Uses `pdftotext -layout` with [[PAGE n]] markers so every citation in the
topic files is traceable. Emits a manifest recording page count, character
count and word count per book, so truncation is detectable at a glance.

Usage:
    python extract_book_corpus.py --books-dir "E:\Trading Books" --out-dir knowledge/_pdf_extract

Requires: pdftotext (poppler-utils).  Install:
    Windows:  choco install poppler    or download from https://github.com/osvalber/poppler-windows
    Linux:    apt install poppler-utils
    macOS:    brew install poppler
"""
import argparse, json, os, re, subprocess, sys, hashlib
from pathlib import Path

# slug → relative PDF path under --books-dir
SLUG_MAP = {
    "brooks_trends": "brooks/Trading Price Action Trends - Technical Analysis of Price Charts Bar by Bar for the Serious Trader 2011.pdf",
    "brooks_ranges": "brooks/Trading Price Action Trading Ranges.pdf",
    "brooks_reversals": "Al Brooks — Trading Price Action Reversals.pdf",
    "grimes_art_science": "grimes/The Art and Science of Technical Analysis - Market Structure, Price Action, and Trading Strategies 2012.pdf",
    "dalton_mind_over_markets": "dalton/Mind_Over_Markets_Power_Trading_with_Market_Generated_Information_Updated_Edition_-_James_F_Dalton.pdf",
    "dalton_markets_in_profile": "dalton/Markets in Profile.pdf",
    "dalton_markets_momentum": "dalton/Markets_and_Momentum_-_James_F_Dalton.pdf",
    "murphy_ta": "murphy/Technical Analysis of the Financial Markets by John J. Murphy.pdf",
    "nison_candlesticks": "nison/Japanese Candlestick Charting Techniques, 2nd Edition, Steve Nison_text.pdf",
    "nison_beyond": "nison/Beyond Candlesticks - New Japanese Charting Techniques Revealed 1994.pdf",
    "lien_fx_sessions": "lien/Day Trading and Swing Trading the Currency Market - Technical and Fundamental Strategies to Profit from Market Moves 2nd edition 2008.pdf",
    "elder_trading_room": "elder/Come Into My Trading Room - A Complete Guide to Trading 2002.pdf",
    "couling_volume": "couling-volume/A Complete Guide To Volume Price Analysis 2013.pdf",
    "person_pivots": "person-pivots/A Complete Guide to Technical Trading Tactics - How to Profit Using Pivot Points, Candlesticks & Other Indicators 2004.pdf",
    "carter_mastering": "Mastering the Trade - Proven Techniques for Profiting from Intraday and Swing Trading Setups 2nd edition 2012 (1) - annotated.pdf",
    "chan_algo_trading": "Algorithmic Trading - Winning Strategies and Their Rationale 2013 - annotated.pdf",
    "douglas_zone": "douglas/Trading in the Zone - Master the Market with Confidence, Discipline and a Winning Attitude 2000.pdf",
    "weis_trades": "weis/Trades About to Happen.pdf",
}


def extract_one(pdf_path: Path, out_path: Path) -> dict:
    """Extract a single PDF via pdftotext -layout, inserting [[PAGE n]] markers."""
    if not pdf_path.exists():
        return {"error": f"not found: {pdf_path}"}

    result = subprocess.run(
        ["pdftotext", "-layout", str(pdf_path), "-"],
        capture_output=True, text=True, timeout=120
    )
    if result.returncode != 0:
        return {"error": f"pdftotext failed: {result.stderr[:200]}"}

    raw = result.stdout

    # Insert [[PAGE n]] markers at form-feed boundaries
    pages = raw.split('\f')
    lines = []
    for i, page in enumerate(pages, 1):
        lines.append(f"[[PAGE {i}]]")
        lines.append(page.rstrip())

    text = "\n".join(lines)
    out_path.write_text(text, encoding="utf-8")

    chars = len(text)
    words = len(text.split())
    md5 = hashlib.md5(text.encode()).hexdigest()

    return {
        "pages": len(pages),
        "chars": chars,
        "words": words,
        "md5": md5,
        "bytes": len(text.encode("utf-8")),
    }


def main():
    parser = argparse.ArgumentParser(description="Extract full-text corpus from Trading Books PDFs")
    parser.add_argument("--books-dir", required=True, help="Path to Trading Books root directory")
    parser.add_argument("--out-dir", required=True, help="Output directory for .txt files and manifest")
    parser.add_argument("--slugs", nargs="*", help="Extract only these slugs (default: all)")
    args = parser.parse_args()

    books_dir = Path(args.books_dir)
    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    slugs = args.slugs if args.slugs else list(SLUG_MAP.keys())
    manifest = []
    errors = []

    for slug in slugs:
        if slug not in SLUG_MAP:
            print(f"  SKIP unknown slug: {slug}")
            continue

        rel = SLUG_MAP[slug]
        pdf_path = books_dir / rel
        out_path = out_dir / f"{slug}.txt"

        print(f"  {slug} ← {rel}")
        info = extract_one(pdf_path, out_path)

        if "error" in info:
            print(f"    ERROR: {info['error']}")
            errors.append({"slug": slug, "error": info["error"]})
        else:
            entry = {"slug": slug, "src": rel, **info}
            manifest.append(entry)
            print(f"    {info['pages']} pages, {info['words']:,} words, {info['bytes']:,} bytes")

    # Write manifest
    manifest_path = out_dir / "corpus_manifest.json"
    manifest_path.write_text(json.dumps(manifest, indent=1, ensure_ascii=False))

    total_words = sum(e["words"] for e in manifest)
    total_chars = sum(e["chars"] for e in manifest)
    print(f"\nDone: {len(manifest)}/{len(slugs)} extracted, {total_words:,} words, {total_chars:,} chars")
    if errors:
        print(f"Errors: {len(errors)}")
        for e in errors:
            print(f"  {e['slug']}: {e['error']}")

    return 0 if not errors else 1


if __name__ == "__main__":
    sys.exit(main())
