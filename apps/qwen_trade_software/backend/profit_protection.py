"""Launcher kept at this path so services, scripts and scheduled tasks keep working.

Implementation: goldflow/management/profit_protection.py
"""
import runpy

if __name__ == "__main__":
    runpy.run_module("goldflow.management.profit_protection", run_name="__main__", alter_sys=True)
