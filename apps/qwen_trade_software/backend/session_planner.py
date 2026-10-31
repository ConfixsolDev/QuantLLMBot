"""Launcher kept at this path so services, scripts and scheduled tasks keep working.

Implementation: goldflow/planning/session_planner.py
"""
import runpy

if __name__ == "__main__":
    runpy.run_module("goldflow.planning.session_planner", run_name="__main__", alter_sys=True)
