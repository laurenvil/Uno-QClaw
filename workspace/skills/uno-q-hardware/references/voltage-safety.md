# Voltage and Safety Rules

The Uno Q is **not a drop-in replacement for the classic Arduino Uno**. Voltage levels differ. Treat every wiring question through this lens.

## The two voltage worlds

| Domain | Voltage | Where it shows up |
|---|---|---|
| MCU I/O (Arduino headers) | **3.3 V** | All JDIGITAL, JANALOG, Qwiic, JSPI pins |
| MCU power rail (header) | 5 V (provided) | "+5V" pin on the headers — for powering external sensors |
| MPU I/O (Linux GPIO) | 1.8 V | Not exposed for sketches; called from Python via Bridge |
| USB-C input | 5 V | Powers the board |
| VIN | 7–24 V | Alternative power input |

**Sketches see only the 3.3 V MCU world.** When a user says "pin", "Wire", or "analogRead", that is 3.3 V.

## The 5 V trap

Classic Uno is 5 V tolerant on I/O. **Uno Q is not.** Common user mistakes:

- Connecting a 5 V sensor (e.g., HC-SR04, DHT11 in 5 V mode) directly to a digital pin → over-voltage on MCU port.
- Wiring a potentiometer with one end on +5 V → A0 sees up to 5 V → damage.
- Using a 5 V level-shifter the wrong way around → output stuck high.

**Always:** if a sensor is described as 5 V, recommend either powering it from the +5 V pin while ensuring its output swings only 0–3.3 V, or interposing a level shifter / voltage divider on its data line.

## ADC range

`analogRead()` maps **0–3.3 V → 0–1023** (12-bit ADC truncated to 10-bit by default for Uno API compatibility).

A reading of `1023` means 3.3 V, not 5 V. If a user is "expecting more range," explain the 3.3 V ceiling.

## MPU vs MCU at a glance

- A sketch (`.ino`) runs on the **MCU**. It cannot directly touch the QRB2210, the camera, the Wi-Fi chip, or any Linux file.
- A Python script on the **MPU** can talk to the MCU via the Bridge API (`from arduino_alvik import ArduinoAlvik` or the Arduino Bridge library), and that is how sketches relay sensor data to / from AI inference.
- When a user asks something that requires Linux (file I/O, network requests, OpenCV), it is an MPU/Python question — say so.

## Safe-by-default phrasing

When uncertain about a sensor, default to: *"On Uno Q, headers are 3.3 V — that is different from the classic Uno. Check this sensor's data sheet for its logic level before connecting."*
