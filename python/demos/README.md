# QClaw Python Demos

Small, self-contained Python scripts that exercise the parts of QClaw's runtime
that App Lab users care about — the MPU↔MCU Bridge, the local llama-server,
the `qclaw` CLI, and the Linux-side sysfs LEDs.

Run each demo from the QClaw app directory or from `~/.qclaw/workspace/python/`
(the symlink that `python/main.py` creates on first boot).

## Demos

| File | What it shows | Requires |
|---|---|---|
| `01_ping_mcu.py` | Call the MCU `ping()` Bridge provider | Sketch flashed |
| `02_flash_led.py` | Call the MCU `flash_led(times)` provider | Sketch flashed |
| `03_query_llm.py` | Direct HTTP call to the local `llama-server` | yzma engine running |
| `04_qclaw_direct.py` | Run a one-shot prompt through `qclaw direct` | `bin/qclaw` staged |
| `05_sysfs_led.py` | Drive the MPU RGB LEDs via `/sys/class/leds` | Linux on the Uno Q |
| `06_scroll_matrix.py` | Scroll text on the LED matrix via `scroll(text)` | Sketch flashed |

> Bridge demos use `from arduino.app_utils import Bridge` — the App-Lab-native
> client. They must run inside App Lab's per-app venv (the daemon installs
> `arduino.app_utils` automatically on first Run).

## Quick start

```bash
# From the App Lab app directory:
python3 python/demos/01_ping_mcu.py
python3 python/demos/03_query_llm.py "Why is the sky blue?"
```

## Symlink behaviour

After `python/main.py` runs once, `~/.qclaw/workspace/python/` is a symlink
back to this directory, so the QClaw agent and the App Lab IDE see the same
files. Edits made from either side land in the same place.
