---
name: wireless
description: Wi-Fi and Bluetooth on the Uno Q — the WCN3980 module exposes dual-band Wi-Fi 5 (802.11a/b/g/n/ac) and Bluetooth 5.1 to the Linux MPU side. Read this BEFORE writing any project that says "connect to Wi-Fi", "send over the network", "HTTP request", "Bluetooth", or "send my sensor data to my phone". The wireless module is owned by Linux — sketches reach the network via Bridge.
---

# Wi-Fi & Bluetooth on the Uno Q

The Uno Q has **one wireless module** — the **Qualcomm WCN3980** (designated U2901 on the board). It provides:

- **Wi-Fi 5** — 802.11a/b/g/n/ac, dual-band (2.4 GHz + 5 GHz)
- **Bluetooth 5.1**

**The wireless module is connected to the MPU (Linux side), not the MCU.** The MCU (STM32U585) has no Wi-Fi or Bluetooth radio. This is the opposite of the classic Arduino UNO R4 WiFi, where the ESP32-S3 co-processor handles wireless and the sketch talks to it directly.

**On the Uno Q, sketches reach the network through Bridge.** Linux owns the radios; Python on Linux makes the HTTP calls / opens the BLE GATT server; the MCU sketch calls Linux via Bridge when it needs to send or receive.

## When to use

| Lesson scenario | Approach |
|---|---|
| "Connect the board to Wi-Fi" | Run `nmcli` on Linux side, or configure during App Lab onboarding — no sketch involvement |
| "POST sensor data to a web API" | Sketch reads sensor → Bridge.notify("data") → Python `requests.post(...)` |
| "Serve a web dashboard for live data" | Python runs Flask/FastAPI, polls MCU via Bridge for values |
| "Phone connects to the board over BLE" | Python runs a BLE GATT server (e.g. `bless` library), forwards reads/writes via Bridge to the sketch |
| "Send a Telegram message when a button is pressed" | MCU notifies on press → Python sends the Telegram message |

## Quick rules

1. **Sketches do NOT include `WiFi.h`.** That library targets the UNO R4 WiFi, not the Uno Q. The Uno Q has no Wi-Fi peripheral on the MCU.
2. **All network I/O happens in Python on the Linux side.** Use `requests` for HTTP, `paho-mqtt` for MQTT, `websockets` for WebSocket, the standard library `socket` for raw TCP/UDP.
3. **Bridge is the bridge** (literally) between the two sides. See `bridge/SKILL.md` for the RPC layer.
4. **Wi-Fi setup is a Linux task.** Use `nmcli`, `wpa_supplicant`, or the App Lab first-time-setup wizard. It is NOT done from a sketch.
5. **Bluetooth uses BlueZ on Linux** (the standard Debian stack). Python wrappers: `bleak` for client-side BLE, `bless` or `dbus-python` for GATT servers.
6. **The Wi-Fi data transport is SDIO; the Bluetooth control is UART** — both internal to the QRB2210 SoC. Users don't see this; they just use Linux network APIs.

## Reference files

- `references/wifi-setup.md` — how to connect the board to a Wi-Fi network from the Linux side.
- `references/bridge-tcp.md` — pattern for shuttling sketch data to a remote server over Wi-Fi using Bridge + Python `requests`.
- `references/bluetooth.md` — Bluetooth Classic and BLE on the Uno Q.

## Pitfalls

- **`#include <WiFi.h>` in a sketch.** Will not compile against `arduino:zephyr:unoq`. There is no MCU Wi-Fi.
- **Trying to do TCP from the sketch.** The sketch has no IP stack. Push data to Python via Bridge and let Python do the network call.
- **Forgetting the dual-band antenna is shared.** Wi-Fi and Bluetooth share one PCB antenna. Heavy Wi-Fi traffic can interrupt BT connections briefly. Use BLE on its own channels (37/38/39) where possible.
- **Hard-coding Wi-Fi credentials into a sketch.** Even if the sketch could connect, that's a security anti-pattern. Credentials live in NetworkManager / `/etc/wpa_supplicant/` on Linux, set up once and forgotten.
- **Confusing the Uno Q with a Raspberry Pi.** Pi has its own `/sys/class/gpio` and Python GPIO libraries. The Uno Q's Linux side does NOT control the Arduino headers — those belong to the MCU. Network on Linux, GPIO on MCU, Bridge between them.

## See also

- `bridge/SKILL.md` — required reading; this skill builds on it.
- `arduino-app-lab/SKILL.md` — App Lab handles initial Wi-Fi credential entry.
- `uno-q-hardware/references/connectors.md` — note that there is no wireless module on any user-facing header; it's a soldered chip.
