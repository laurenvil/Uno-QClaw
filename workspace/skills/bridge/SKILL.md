---
name: bridge
description: Arduino Bridge — software RPC layer that connects Python on the MPU (Linux side) with Arduino sketches on the MCU (STM32U585). Read this BEFORE writing any project that combines a Python program with an Arduino sketch, or that asks "how do I send data from my sketch to the Linux side?". The Uno Q is two processors on one board; Bridge is how they talk.
---

# Bridge — Inter-Processor RPC on the Uno Q

The Arduino Uno Q is **two computers on one board**:

- **MPU** (Qualcomm QRB2210, 4× Cortex-A53 @ 2.0 GHz, Debian Linux) — runs Python, web servers, AI models, OpenCV.
- **MCU** (STMicroelectronics STM32U585, Cortex-M33 @ 160 MHz, Zephyr + Arduino Core) — runs `.ino` sketches, controls every Arduino header pin (digital I/O, PWM, ADC, I²C, SPI, UART, CAN).

**Bridge** is Arduino's software-based **Remote Procedure Call (RPC)** layer that lets either side call functions on the other:

```
Python (Linux side)                Arduino sketch (MCU side)
─────────────────                  ─────────────────────────
from bridge import ...             #include <Bridge.h>
result = bridge.call("read_A0")    Bridge.begin();
print(result)                      // expose a service the Python can call
```

Without Bridge, users treat the Uno Q like a classic Arduino and never use the Linux side. The whole point of this board is the combination.

## When to use

Use Bridge when a project needs **both** sides:

| Lesson scenario | Why Bridge |
|---|---|
| Python program reads a sensor wired to A0 | MCU owns the pin; Python calls MCU via Bridge |
| Arduino sketch wants to fetch weather data from the internet | MCU has no Wi-Fi; MCU calls MPU via Bridge, MPU hits the network |
| AI model on Linux decides when to blink an LED | Python runs the model, calls MCU to drive the LED |
| Sketch streams accelerometer data to a web dashboard | MCU samples 200 Hz, MPU serves the HTTP/WebSocket UI |
| Voice assistant on the board | Mic + speech-to-text on Linux; servo control via MCU |

**Don't use Bridge** when only one side is involved:
- Pure GPIO/PWM/sensor work → write a normal Arduino sketch, no Linux.
- Pure web scraping / AI inference / file processing → write a Python program, no MCU.

## Quick rules

1. **Bridge runs over a physical transport.** USB CDC (virtual serial port), UART, or SPI. The default in App Lab is USB CDC.
2. **Either side can expose a service.** The other side calls it by name with arguments and receives a structured response.
3. **Either side can push notifications** (one-way events) for asynchronous things — button presses, sensor thresholds.
4. **Bridge.begin() must be called in setup()** before any RPC call from the MCU side. Forgetting this leaves both sides waiting forever.
5. **Type-safe API.** Arguments and return values are typed; the wire format handles serialization. You don't write `Serial.print` glue code.
6. **Latency is ~1–5 ms per call** over USB CDC. Fast enough for control loops at 100 Hz, not for hard real-time deadlines under 1 ms (do that in the sketch alone).

## How a project is structured (Arduino App Lab)

An **App** in App Lab combines:

```
my-app/
├── main.py              ← runs on the Linux MPU
├── sketch.ino           ← runs on the STM32U585 MCU
└── bricks/              ← optional pre-packaged services (AI models, web UIs)
```

When the user presses **Run** in App Lab:
1. App Lab compiles the `.ino` and flashes the MCU (via the same OpenOCD path the `arduino` tool uses, sketch partition `0x8100000`).
2. App Lab starts `main.py` on the Linux side.
3. Both processes initialize Bridge — `Bridge.begin()` on the MCU, `from bridge import ...` on the Python side.
4. They start exchanging messages.

## Reference files

- `references/python-side.md` — how to call MCU services from Python, set up Bridge clients, handle notifications.
- `references/mcu-side.md` — how to expose services from an `.ino` sketch and push notifications back to Linux.
- `references/examples.md` — three complete worked examples (sensor relay, AI-controlled LED, button-triggered web request).

## Pitfalls

- **Confusing MCU GPIO with MPU GPIO.** The Arduino headers (D0–D21, A0–A5) are MCU pins. Linux can NOT `import RPi.GPIO`-style drive them; it must call the MCU via Bridge.
- **Treating the Uno Q like a Raspberry Pi.** Linux on the QRB2210 has its own GPIO at 1.8 V on JMISC, but those are mostly system-reserved (camera, audio, MPU SoC functions). The user-facing pins belong to the MCU.
- **Forgetting `Bridge.begin()`.** Both sides will hang silently. Always include it in `setup()`.
- **Hot-plugging USB during a Bridge call.** USB CDC drops; the call returns an error. Catch it on both sides.
- **Confusing Bridge with Serial.** `Serial.print` writes to USART1 (or USB CDC depending on configuration); Bridge has its own framing on top. Use `Bridge.print` / `bridge.log()` to send debug strings through the framed channel.

## See also

- The MPU/MCU split is documented in `uno-q-hardware/SKILL.md`.
- For uploading sketches without Bridge involvement (single-side `.ino` only), see `sketch-patterns/references/upload.md`.
- For the App Lab workflow that wraps Bridge, see `arduino-app-lab/SKILL.md`.
