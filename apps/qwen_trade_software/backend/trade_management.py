"""Launcher kept at this path so services, scripts and scheduled tasks keep working.

Implementation: goldflow/management/trade_management.py
"""
import runpy

if __name__ == "__main__":
    runpy.run_module("goldflow.management.trade_management", run_name="__main__", alter_sys=True)
