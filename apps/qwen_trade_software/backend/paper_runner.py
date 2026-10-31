"""Launcher kept at this path so services, scripts and scheduled tasks keep working.

Implementation: goldflow/execution/paper_runner.py
"""
import runpy

if __name__ == "__main__":
    runpy.run_module("goldflow.execution.paper_runner", run_name="__main__", alter_sys=True)
