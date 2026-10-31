"""Launcher kept at this path so services, scripts and scheduled tasks keep working.

Implementation: goldflow/runtime/software_runtime.py
"""
import runpy

if __name__ == "__main__":
    runpy.run_module("goldflow.runtime.software_runtime", run_name="__main__", alter_sys=True)
