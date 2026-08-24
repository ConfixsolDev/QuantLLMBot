"""Independent intraday market-story observer.

The package owns observation and reflection only.  Its sole integration surface
is the versioned, read-only contract exposed by :mod:`contracts`.
"""

from .contracts import CONTRACT_VERSION, read_for_trader

__all__ = ["CONTRACT_VERSION", "read_for_trader"]
