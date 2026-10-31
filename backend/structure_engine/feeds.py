"""Recorded bar source for back-tests.

``RecordedFeed`` streams CLOSED M1 bars, oldest first, from CSV/TSV/JSONL files
or whole folders of them. Live MT5 bars come from the application
(``quantllm.market_feed``), which pushes them into the very same engine — the
engine cannot tell the two apart (Rule 2: live == test).
"""

from __future__ import annotations

from pathlib import Path
from typing import Callable, Iterator

from .bars import Bar, load_m1


class RecordedFeed:
    """Replay recorded M1 files in time order.

    ``paths`` may be files and/or folders; a folder contributes every
    ``*.csv`` / ``*.tsv`` / ``*.jsonl`` inside it, in name order (monthly
    files named YYYY-MM sort correctly). Any bar not newer than the previous
    one is skipped, so overlapping exports cannot break the stream.
    ``time_shift`` converts broker-clock timestamps to UTC if a file is not UTC.
    """

    def __init__(self, paths, *, time_shift: Callable[[int], int] | None = None,
                 start: int | None = None, end: int | None = None) -> None:
        if isinstance(paths, (str, Path)):
            paths = [paths]
        files: list[Path] = []
        for p in map(Path, paths):
            if p.is_dir():
                files += sorted(x for x in p.iterdir() if x.suffix.lower() in (".csv", ".jsonl", ".tsv"))
            else:
                files.append(p)
        self.files, self.start, self.end, self.time_shift = files, start, end, time_shift

    def __iter__(self) -> Iterator[Bar]:
        last = None
        for f in self.files:
            for bar in load_m1(f, time_shift=self.time_shift, start=self.start, end=self.end):
                if last is not None and bar.time <= last:
                    continue
                last = bar.time
                yield bar
