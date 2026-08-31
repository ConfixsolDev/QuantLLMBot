"""Execution safety boundary; intentionally contains no broker submission."""

from .boundary import validate_candidate_for_execution

__all__ = ["validate_candidate_for_execution"]
