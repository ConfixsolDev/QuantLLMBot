from __future__ import annotations

import sys
import unittest
from pathlib import Path


BACKEND = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND))

from gpu_placement import (  # noqa: E402
    GpuPlacementRequired,
    classify_residency,
    recovery_action,
    require_gpu_residency,
)


class Response:
    def __init__(self, payload: bytes):
        self.payload = payload

    def __enter__(self):
        return self

    def __exit__(self, *_):
        return False

    def read(self):
        return self.payload


class GpuOnlyPolicyTests(unittest.TestCase):
    model = "qwen-trading-v004:latest"

    def test_classifies_full_gpu_only(self):
        full = [{"name": self.model, "size": 10e9, "size_vram": 10e9}]
        mixed = [{"name": self.model, "size": 10e9, "size_vram": 5e9}]
        cpu = [{"name": self.model, "size": 10e9, "size_vram": 0}]
        self.assertEqual(classify_residency(full, self.model)["state"], "gpu")
        self.assertEqual(classify_residency(mixed, self.model)["state"], "mixed")
        self.assertEqual(classify_residency(cpu, self.model)["state"], "cpu")
        self.assertEqual(classify_residency([], self.model)["state"], "unloaded")

    def test_matches_model_keyed_rows_not_only_name_keyed(self):
        """2026-08-28: Ollama /api/ps rows keyed 'model' instead of 'name'
        (an Ollama version/schema difference) made every row look nameless,
        so this always reported 'unloaded' regardless of true GPU state."""
        rows = [{"model": self.model, "size": 10e9, "size_vram": 10e9}]
        self.assertEqual(classify_residency(rows, self.model)["state"], "gpu")

    def test_case_and_tag_variance_still_matches(self):
        rows = [{"name": self.model.upper(), "size": 10e9, "size_vram": 10e9}]
        self.assertEqual(classify_residency(rows, self.model)["state"], "gpu")

    def test_gate_rejects_every_non_gpu_state(self):
        def opener(*_, **__):
            return Response(
                b'{"models":[{"name":"qwen-trading-v004:latest",'
                b'"size":10000000000,"size_vram":0}]}'
            )

        with self.assertRaises(GpuPlacementRequired):
            require_gpu_residency(self.model, owner="test", opener=opener)

    def test_supervisor_restarts_cpu_and_warms_unloaded(self):
        self.assertEqual(
            recovery_action(desired_loaded=True, state="cpu"), "restart_ollama"
        )
        self.assertEqual(
            recovery_action(desired_loaded=True, state="mixed"), "restart_ollama"
        )
        self.assertEqual(
            recovery_action(desired_loaded=True, state="unloaded"), "warm_model"
        )
        self.assertEqual(
            recovery_action(desired_loaded=True, state="gpu"), "none"
        )
        self.assertEqual(
            recovery_action(desired_loaded=False, state="cpu"), "none"
        )

    def test_both_generation_paths_enforce_the_shared_gate(self):
        shared = (BACKEND / "review_shared.py").read_text(encoding="utf-8")
        context = (BACKEND / "market_context_cache.py").read_text(encoding="utf-8")
        self.assertIn("require_gpu_residency(", shared)
        self.assertIn('owner="review_shared.ollama_generate"', shared)
        self.assertIn("require_gpu_residency(", context)
        self.assertIn('owner="market_context_cache"', context)


if __name__ == "__main__":
    unittest.main()
