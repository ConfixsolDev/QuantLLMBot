"""Single source of truth for live trading runtime identity.

Upgrade or roll back Qwen by changing ``DEFAULT_QWEN_MODEL`` here. Every live
worker imports ``ACTIVE_QWEN_MODEL``; ``QWEN_MODEL`` remains an intentional
deployment override for qualification and controlled comparisons.
"""

from __future__ import annotations

import os


# Change this one constant when promoting the next trained model.
DEFAULT_QWEN_MODEL = "qwen-trading-v004:latest"

# All processes resolve the override identically at startup.
ACTIVE_QWEN_MODEL = os.environ.get("QWEN_MODEL", DEFAULT_QWEN_MODEL)
