#!/usr/bin/env python3
"""Run every test module and report once.

There is no pytest dependency here deliberately: each module runs standalone
so a single suite can be checked without installing anything, and this just
collects them.
"""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent


def main() -> int:
    modules = sorted(p for p in HERE.glob("test_*.py"))
    failed = []
    for module in modules:
        result = subprocess.run([sys.executable, str(module)],
                                capture_output=True, text=True)
        status = "ok  " if result.returncode == 0 else "FAIL"
        print(f"{status}  {module.name}")
        if result.returncode != 0:
            failed.append(module.name)
            print(result.stdout.rstrip())
            print(result.stderr.rstrip())
    print(f"\n{len(modules) - len(failed)}/{len(modules)} modules pass")
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
