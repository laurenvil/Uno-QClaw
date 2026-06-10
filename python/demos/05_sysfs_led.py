#!/usr/bin/env python3
"""Drive the MPU RGB LEDs directly via `/sys/class/leds`.

The Uno Q's onboard user LEDs (red/green/blue) are wired to the Qualcomm SoC
side of the board and exposed as standard Linux sysfs LED devices. They use
active-low brightness — writing the trigger's max value turns the LED off.

This script blinks each colour twice without involving the MCU.

Usage:
    python3 python/demos/05_sysfs_led.py
    python3 python/demos/05_sysfs_led.py --colour red
    python3 python/demos/05_sysfs_led.py --cycles 5
"""
from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path

LED_BASE = Path("/sys/class/leds")
COLOURS = {
    "red":   ["red", "led_r", "user-red"],
    "green": ["green", "led_g", "user-green"],
    "blue":  ["blue", "led_b", "user-blue"],
}


def find_led(colour: str) -> Path | None:
    for name in COLOURS[colour]:
        candidate = LED_BASE / name
        if candidate.exists():
            return candidate
    # Fall back to any LED matching the colour as a substring
    if LED_BASE.exists():
        for entry in LED_BASE.iterdir():
            if colour in entry.name.lower():
                return entry
    return None


def blink(led: Path, on_ms: int, off_ms: int) -> None:
    brightness = led / "brightness"
    max_path = led / "max_brightness"
    max_val = int(max_path.read_text().strip()) if max_path.exists() else 255
    brightness.write_text(str(max_val))
    time.sleep(on_ms / 1000.0)
    brightness.write_text("0")
    time.sleep(off_ms / 1000.0)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--colour", choices=list(COLOURS) + ["all"], default="all")
    parser.add_argument("--cycles", type=int, default=2)
    parser.add_argument("--on-ms", type=int, default=200)
    parser.add_argument("--off-ms", type=int, default=200)
    args = parser.parse_args()

    targets = list(COLOURS) if args.colour == "all" else [args.colour]
    leds = [(c, find_led(c)) for c in targets]
    missing = [c for c, path in leds if path is None]
    if missing:
        print(f"ERROR: no /sys/class/leds entry for: {', '.join(missing)}")
        print("       Run `ls /sys/class/leds` — names vary by Linux build.")
        return 1

    for cycle in range(args.cycles):
        for colour, path in leds:
            try:
                blink(path, args.on_ms, args.off_ms)
            except PermissionError:
                print(f"ERROR: cannot write to {path}/brightness (root required?)")
                return 2
            print(f"  cycle {cycle + 1}: {colour} ({path.name})")
    return 0


if __name__ == "__main__":
    sys.exit(main())
