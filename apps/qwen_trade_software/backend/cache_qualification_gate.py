"""Launcher kept at this path so services, scripts and scheduled tasks keep working.

Implementation: goldflow/market/cache_qualification_gate.py
"""
import runpy

if __name__ == "__main__":
    runpy.run_module("goldflow.market.cache_qualification_gate", run_name="__main__", alter_sys=True)
