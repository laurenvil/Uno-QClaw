# Deploying an App in App Lab

The full lifecycle from "create" to "running on the board".

## 1. Create or open an App

In App Lab:
- **New App** — pick a template (Hello World, sensor relay, vision demo, etc.) or start blank.
- **Open App** — load an existing project from your file system.

The App opens in App Lab's editor with two tabs:
- **Linux side** — `main.py` and any Python helpers.
- **Sketch** — `sketch.ino` and any `.h` / `.cpp` files.

## 2. Add Bricks (optional)

If your App needs an AI model, web UI, or pre-packaged service, click **Add Brick**, pick from the catalog, and App Lab installs it into `bricks/`.

See `bricks.md` for the patterns.

## 3. Configure Wi-Fi (first run, SBC mode only)

On first run in Single-Board Computer (SBC) mode, App Lab prompts for Wi-Fi credentials. These are written to NetworkManager and the board will reconnect automatically on subsequent boots.

In PC-hosted mode, this step is skipped — the PC's network is used.

## 4. Press Run

This kicks off:

1. **Cross-compile the sketch** for `arduino:zephyr:unoq`. Compile errors stop the launch and show up in the **Start-up** console.
2. **Flash the MCU** via OpenOCD at sketch partition `0x8100000`. (Same path QClaw's `arduino` tool uses.)
3. **Deploy the Linux component** — copy `main.py` and any Bricks to the board's working directory (in SBC mode this is local; in PC-hosted mode it's pushed over USB CDC or LAN).
4. **Start any Bricks** as Linux services.
5. **Run `main.py`** on the Linux side.
6. **Bridge initializes** on both sides — `Bridge.begin()` on the MCU, `from arduino import Bridge` on the Python side.

## 5. Monitor with the three console tabs

App Lab shows three tabs while an App runs:

| Tab | Content |
|---|---|
| **Start-up** | Compile output, flash status, Brick start logs, Bridge init |
| **Main (Python®)** | `print()` from `main.py`; tracebacks if Python crashes |
| **Sketch (Microcontroller)** | `Serial.println()` from the sketch; `Bridge.log()` calls |

An App can start successfully (Start-up green) and still fail at runtime — check Main and Sketch tabs for runtime errors.

## 6. Iterate

After editing, press Run again. App Lab rebuilds and redeploys both sides. The MCU re-flashes only if the sketch changed.

## 7. Stop

Click **Stop** in App Lab. This kills the Python process and any Bricks; the MCU sketch keeps running (the LED keeps blinking, the servo keeps holding position) until you flash a new sketch or power-cycle the board.

## Deploying from PC-hosted vs SBC mode

| Mode | What happens |
|---|---|
| **PC-hosted** | App Lab runs on your laptop/desktop. Code is pushed to the Uno Q over USB-C data, board reports status back. |
| **SBC** | App Lab runs on the Uno Q itself, served as a web UI accessed from your laptop's browser. No USB data link required after Wi-Fi is set up. |

PC-hosted is the default for first-time setup. SBC mode is the production workflow once Wi-Fi is configured.

## How this relates to QClaw

QClaw's `arduino` tool does steps 1+2 (compile + flash) for a single sketch. It does NOT do steps 3–5 (multi-file Apps, Bricks, Python deployment).

A user can use QClaw to iterate quickly on the sketch portion, then move into App Lab when they need the full App workflow (Python integration, Bricks, multiple files).

## Pitfalls

- **Run button greys out.** App Lab is still busy from the previous deploy. Wait for the Start-up tab to settle.
- **"Brick failed to start"** in Start-up tab. Brick dependency missing. Check the Brick's requirements (network access, model file size).
- **Python runs but Bridge calls hang.** MCU sketch missing `Bridge.begin()` in `setup()` or `Bridge.poll()` in `loop()`. Add both. (See `bridge/references/mcu-side.md`.)
- **Sketch compiles but doesn't flash.** OpenOCD couldn't reach the MCU. Power-cycle the board; if it persists, check the SWD wiring on the carrier board.
- **App runs once, fails on second Run.** Some Bricks bind ports (web UI on :8000) and don't release cleanly on stop. Wait 30 seconds before re-running, or change the port.

## See also

- `bricks.md` for the Brick model.
- `bridge/SKILL.md` because the App architecture is built on Bridge.
- `sketch-patterns/references/upload.md` for the equivalent QClaw-side flow on the sketch portion only.
