---
name: linux-led
description: Linux sysfs LED control — drive the Uno Q's MPU-side RGB LEDs (RGB LED 1 and RGB LED 2) from Python with no sketch involvement. Read this when the user wants to blink or color a board LED using only Python on the Linux side, or asks about the SoC LEDs / panic LED / WLAN LED / Bluetooth LED. The MCU-side RGB LEDs (LED 3 and LED 4) use a sketch instead — see `sketch-patterns/SKILL.md`.
---

# Linux sysfs LED control on the Uno Q

The Uno Q has **four RGB LEDs**. Two are owned by the Linux MPU side and are controlled via the Linux LED class subsystem (`/sys/class/leds/`); two are owned by the Arduino MCU side and are controlled by a sketch.

| LED | Where it's wired | Controlled how |
|---|---|---|
| **RGB LED 1** (D27301) | MPU GPIOs 41 / 42 / 60 | `/sys/class/leds/{red,green,blue}:user/brightness` |
| **RGB LED 2** (D27302) | MPU GPIOs 39 / 40 / 47 | `/sys/class/leds/{red:panic,green:wlan,blue:bt}/brightness` |
| **RGB LED 3** (D27401) | MCU pins PH10 / PH11 / PH12 | `analogWrite()` / `digitalWrite()` from a sketch |
| **RGB LED 4** (D27402) | MCU pins PH13 / PH14 / PH15 | `analogWrite()` / `digitalWrite()` from a sketch |

**The RGB LEDs are active-low.** Write `0` to turn ON; write the max brightness value (255) to turn OFF. This is the opposite of what you might expect.

## When to use Linux LEDs

Use the MPU-side LEDs (LED 1, LED 2) when:
- You're writing a pure Python program with no sketch involvement.
- You want to indicate Linux-side state (a Python service is running, an inference is in progress, an error occurred).
- The user is learning Linux/Python before they get to writing sketches.

Use the MCU-side LEDs (LED 3, LED 4) when:
- The sketch is the primary program and the LED status reflects MCU state.
- You need precise timing (microsecond-accurate blink rates).

## Canonical pattern — blink RGB LED 1 red

```python
# Linux side — no sketch required
import time

def set_led(channel, value):
    """channel = 'red:user' / 'green:user' / 'blue:user' for RGB LED 1.
       value = 0 (ON, active-low) up to 255 (OFF)."""
    with open(f"/sys/class/leds/{channel}/brightness", "w") as f:
        f.write(str(value))

while True:
    set_led("red:user", 0)       # ON (active-low)
    time.sleep(0.5)
    set_led("red:user", 255)     # OFF
    time.sleep(0.5)
```

## Canonical pattern — cycle through colors

```python
import time

def set_color(r, g, b):
    """Set RGB LED 1 to a 0–255 per-channel color, accounting for active-low."""
    for ch, val in [("red:user", r), ("green:user", g), ("blue:user", b)]:
        with open(f"/sys/class/leds/{ch}/brightness", "w") as f:
            f.write(str(255 - val))   # invert: 255 - value = active-low

# Red → Green → Blue → off
for r, g, b in [(255,0,0), (0,255,0), (0,0,255), (0,0,0)]:
    set_color(r, g, b)
    time.sleep(0.5)
```

## Querying the kernel for which LEDs exist

```bash
ls /sys/class/leds/
```

Typical output on the Uno Q:

```
blue:bt    blue:user   green:user   green:wlan   red:panic   red:user
```

`*:user` is RGB LED 1 (free for application use). `*:bt`, `*:wlan`, `*:panic` are RGB LED 2, normally driven by system services (Bluetooth status, Wi-Fi status, kernel panic). You CAN override them but expect the system to fight you for control.

## Permissions

The `/sys/class/leds/*/brightness` files are normally owned by `root`. To write them as a regular user, either:

1. **Add a udev rule** to grant the `gpio` group write access:

```bash
sudo tee /etc/udev/rules.d/99-uno-q-leds.rules <<EOF
SUBSYSTEM=="leds", ACTION=="add", \\
  RUN+="/bin/sh -c 'chgrp gpio /sys/class/leds/*/brightness; chmod g+w /sys/class/leds/*/brightness'"
EOF
sudo udevadm control --reload
sudo udevadm trigger --subsystem-match=leds
sudo usermod -a -G gpio $USER       # then log out and back in
```

2. **Run the Python program as root** (only for prototyping, never for deployed apps).

The official App Lab deployment runs your Python as a user in the `gpio` group, so option 1 is the production path.

## Trigger modes (built-in patterns without Python)

The Linux LED subsystem can drive its own patterns without any code:

```bash
# Heartbeat (double-blink)
echo heartbeat | sudo tee /sys/class/leds/red:user/trigger

# Linked to disk activity
echo disk-activity | sudo tee /sys/class/leds/green:user/trigger

# Linked to CPU activity (if available)
echo cpu | sudo tee /sys/class/leds/blue:user/trigger

# Back to plain on/off control
echo none | sudo tee /sys/class/leds/red:user/trigger
```

List available triggers:

```bash
cat /sys/class/leds/red:user/trigger
```

## Pitfalls

- **Forgetting active-low inversion.** Writing `255` turns the LED OFF; writing `0` turns it ON. Easy to get backwards and conclude "my code doesn't work".
- **Permissions error: "Permission denied".** You need either root or a udev rule. See above.
- **Fighting the kernel for RGB LED 2.** `blue:bt`, `green:wlan`, `red:panic` are driven by system services. You can override them but they'll bounce back when the underlying state changes.
- **Confusing this with the MCU LEDs.** The MPU LEDs (1 and 2) are accessible from Python on Linux. The MCU LEDs (3 and 4) require a sketch. There is no Python API for the MCU LEDs without going through Bridge.

## See also

- `bridge/SKILL.md` — for combining MPU LED control with MCU events.
- `sketch-patterns/SKILL.md` — for MCU-side LED patterns (the other two LEDs).
- For an LLM-callable tool that writes these sysfs files, see the `sysfs_led` tool.
