#!/usr/bin/env python3
"""Wrap `qclaw direct` for a quick non-agentic one-shot query.

`qclaw direct` runs the pre-router + a single LLM call (no tool loop). It's
faster than the agentic path and good for Q&A. This demo shells out to the
binary that App Lab staged into `bin/qclaw`.

Usage:
    python3 python/demos/04_qclaw_direct.py "What pin drives the LED matrix?"
"""
from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

APP_DIR = Path(__file__).resolve().parents[2]
QCLAW_BIN = APP_DIR / "bin" / "qclaw"


def main(argv: list[str]) -> int:
    if not QCLAW_BIN.exists():
        print(f"ERROR: {QCLAW_BIN} not found.")
        print("       Run scripts/build-for-applab.sh or stage binaries into bin/.")
        return 1

    prompt = " ".join(argv[1:]).strip() or "Say hello from the Uno Q."

    env = os.environ.copy()
    env.setdefault("QCLAW_HOME", str(Path.home() / ".qclaw"))

    print(f"$ {QCLAW_BIN.name} direct --model yzma -m {prompt!r}")
    try:
        subprocess.run(
            [str(QCLAW_BIN), "direct", "--model", "yzma", "-m", prompt],
            check=True,
            env=env,
            cwd=str(APP_DIR),
        )
    except subprocess.CalledProcessError as exc:
        print(f"qclaw direct exited with code {exc.returncode}")
        return exc.returncode
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
