#!/usr/bin/env python3
"""Flash the MCU's built-in LED via Bridge.

Calls `flash_led(times)` registered by `sketch/sketch.ino`. The return
value is the number of flashes the MCU performed (echoed back from the
sketch).

Usage:
    python3 python/demos/02_flash_led.py [times]

Examples:
    python3 python/demos/02_flash_led.py        # 3 flashes (default)
    python3 python/demos/02_flash_led.py 10     # 10 flashes
"""
from __future__ import annotations

import sys


def main(argv: list[str]) -> int:
    times = int(argv[1]) if len(argv) > 1 else 3
    if times < 1 or times > 100:
        print("times must be in the range 1..100")
        return 1

    try:
        from arduino.app_utils import Bridge
    except ImportError:
        print("ERROR: arduino.app_utils not available — run inside Arduino App Lab.")
        return 1

    print(f"Flashing built-in LED {times} times via Bridge…")
    try:
        echoed = Bridge.call("flash_led", times, timeout=times + 5)
    except Exception as exc:
        print(f"flash_led() failed: {exc}")
        return 2

    print(f"MCU acknowledged {echoed} flashes.")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
