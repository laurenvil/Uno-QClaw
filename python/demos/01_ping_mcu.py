#!/usr/bin/env python3
"""Call the MCU `ping` Bridge provider.

sketch/sketch.ino registers three Bridge providers:

    Bridge.provide("ping",      ping);       // returns 1
    Bridge.provide("flash_led", flash_led);  // flashes built-in LED N times
    Bridge.provide("scroll",    scroll);     // scrolls text on the LED matrix

This script invokes `ping` from the Linux side and prints the result.
Requires the sketch to be flashed (App Lab does this when the user clicks
Run on the QClaw app).

Usage:
    python3 python/demos/01_ping_mcu.py
"""
from __future__ import annotations

import sys


def main() -> int:
    try:
        from arduino.app_utils import Bridge
    except ImportError:
        print("ERROR: arduino.app_utils is not installed.")
        print("       It ships inside the per-app venv App Lab builds on first run.")
        print("       Run this script from inside the App Lab runtime.")
        return 1

    try:
        result = Bridge.call("ping", timeout=3)
    except Exception as exc:  # BridgeError / TimeoutError / ValueError
        print(f"ping() failed: {exc}")
        print("Is the sketch flashed and is the MCU responding?")
        return 2

    print(f"MCU ping returned: {result}")
    return 0 if result == 1 else 3


if __name__ == "__main__":
    sys.exit(main())
