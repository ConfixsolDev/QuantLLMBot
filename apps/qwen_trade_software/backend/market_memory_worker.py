"""Launcher kept at this path so services, scripts and scheduled tasks keep working.

Implementation: goldflow/market/market_memory_worker.py
"""
import runpy

if __name__ == "__main__":
    runpy.run_module("goldflow.market.market_memory_worker", run_name="__main__", alter_sys=True)
