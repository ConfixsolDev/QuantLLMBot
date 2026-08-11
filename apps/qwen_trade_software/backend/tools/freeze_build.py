#!/usr/bin/env python3
"""Declare, inspect, or clear the frozen build.

2026-08-11 -- what freezing is for
----------------------------------
A study of 71 closed trades could conclude nothing, because the code changed on
every one of the four days it covered. Confidence band, structure metadata and
side mix were each confounded with the day, so "high confidence loses money"
was really "2026-08-10 lost money".

Freezing does not make results arrive faster. At a per-trade standard deviation
of 152 against a mean of -14, detecting a +$20/trade improvement needs roughly
900 trades per arm regardless. Freezing makes those trades ACCUMULATE INTO ONE
SAMPLE instead of four incomparable ones.

Declare the freeze only after a full live session has been verified on the
current build. The baseline should be a system you have watched work.

Usage
-----
    python tools/freeze_build.py                 # show current vs frozen
    python tools/freeze_build.py --declare       # freeze the running build
    python tools/freeze_build.py --clear         # unfreeze (development)
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

BACKEND = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BACKEND))

import build_manifest  # noqa: E402


def show() -> None:
    current = build_manifest.MANIFEST
    frozen = build_manifest.load_frozen()

    print("=" * 74)
    print(" BUILD STATE")
    print("=" * 74)
    print(f"\n  running build : {current['build_id']}")
    print(f"  model         : {current['model']}")
    print(f"  contract      : {current['contract_hash']}")

    if not frozen:
        print("\n  NO FREEZE DECLARED.")
        print("  Results are not yet accumulating into a comparable sample.")
        print("  Declare one with --declare once a live session looks right.")
        return

    print(f"\n  frozen build  : {frozen['build_id']}")
    print(f"  declared at   : {frozen.get('declared_at_utc', 'unknown')}")

    drift = build_manifest.drift_fields(frozen)
    if not drift:
        print("\n  MATCHES THE FREEZE. Results from this build are comparable.")
        return

    print(f"\n  DRIFTED — {len(drift)} difference(s) from the declared freeze:")
    for item in drift:
        print(f"    {item}")
    print("\n  Trades produced now must NOT be pooled with frozen-build results.")
    print("  Either revert the change, or re-declare the freeze and start a")
    print("  fresh sample. Do not average across the two.")


def declare() -> None:
    manifest = dict(build_manifest.compute())
    manifest["declared_at_utc"] = manifest["computed_at_utc"]
    build_manifest.FROZEN_FILE.write_text(
        json.dumps(manifest, indent=2, sort_keys=True), encoding="utf-8"
    )
    print(f"Frozen at build {manifest['build_id']}")
    print(f"  written to {build_manifest.FROZEN_FILE}")
    print("\nFrom now on, any change to the decision-relevant modules or their")
    print("tunables will log an ERROR at startup naming exactly what moved.")
    print("Strategy work continues through parameters — which are part of the")
    print("manifest, so a threshold change shows up as a new build rather than")
    print("as an invisible one.")


def clear() -> None:
    if build_manifest.FROZEN_FILE.exists():
        build_manifest.FROZEN_FILE.unlink()
        print("Freeze cleared. Drift alarms are off; results will no longer be")
        print("comparable across changes.")
    else:
        print("No freeze was declared.")


def main() -> int:
    parser = argparse.ArgumentParser()
    group = parser.add_mutually_exclusive_group()
    group.add_argument("--declare", action="store_true")
    group.add_argument("--clear", action="store_true")
    args = parser.parse_args()

    if args.declare:
        declare()
    elif args.clear:
        clear()
    else:
        show()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
