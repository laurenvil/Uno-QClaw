#!/usr/bin/env python3
"""Scroll text on the LED matrix via Bridge.

Calls `scroll(text)` registered by `sketch/sketch.ino`. The return value
is the character count the MCU received — useful for confirming the
string round-tripped intact.

Usage:
    python3 python/demos/06_scroll_matrix.py "Hello, world"
    python3 python/demos/06_scroll_matrix.py                # default text
"""
from __future__ import annotations

import sys


def main(argv: list[str]) -> int:
    text = " ".join(argv[1:]) if len(argv) > 1 else "Hello from QClaw"

    try:
        from arduino.app_utils import Bridge
    except ImportError:
        print("ERROR: arduino.app_utils not available — run inside Arduino App Lab.")
        return 1

    print(f"Scrolling on LED matrix: {text!r}")
    try:
        length = Bridge.call("scroll", text, timeout=5)
    except Exception as exc:
        print(f"scroll() failed: {exc}")
        return 2

    print(f"MCU rendered {length} characters.")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
