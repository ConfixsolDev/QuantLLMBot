"""Modular V2 implementation layer.

This package is intentionally inactive by default.  It provides stable
boundaries around the tested backend components so the live runtime can be
switched one boundary at a time after parity evidence is recorded.
"""

__all__ = ["integration", "market", "storage", "strategy", "execution"]
