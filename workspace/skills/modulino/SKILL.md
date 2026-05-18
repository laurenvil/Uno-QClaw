---
name: modulino
description: Arduino Modulino nodes — plug-and-play I²C sensors and actuators that connect to the Qwiic connector on the Uno Q. Read this when the user mentions a Modulino by name (Buzzer, Distance, Knob, Movement, Pixels, Thermo, Touch) or says "I have a Qwiic-connected sensor". Each Modulino has a known I²C address and a published Arduino library.
---

# Modulino — Plug-and-play sensors for the Uno Q

**Modulino** is Arduino's plug-and-play sensor ecosystem. Each Modulino is a small board with a JST-SH Qwiic connector. Plug one (or a chain of several) into the Qwiic connector on the Uno Q — no breadboard, no soldering, no resistor calculations.

The Qwiic connector on the Uno Q is **I²C4** on the MCU side, at 3.3 V:

| Qwiic pin | MCU pin | Function |
|---|---|---|
| GND | GND | Ground |
| 3V3 | PWR_3P3V | 3.3 V power |
| SDA | PD13 | I²C4 data |
| SCL | PD12 | I²C4 clock |

In an Arduino sketch this is accessed via `Wire.h` (the default `Wire` instance maps to I²C4 when the Modulino library is loaded), or via the dedicated `Modulino` library.

## The Modulino catalog

| Modulino | What it does | I²C address | Library class |
|---|---|---|---|
| **Modulino Buzzer** | Piezo buzzer for tones | 0x3C | `ModulinoBuzzer` |
| **Modulino Distance** | Time-of-flight distance sensor (VL53L4CD, ~4 m range) | 0x29 | `ModulinoDistance` |
| **Modulino Knob** | Rotary encoder with push button | 0x76 | `ModulinoKnob` |
| **Modulino Movement** | 6-DoF IMU (accelerometer + gyro) | 0x6A | `ModulinoMovement` |
| **Modulino Pixels** | 8 RGB LEDs in a row | 0x6C | `ModulinoPixels` |
| **Modulino Thermo** | Temperature + humidity (HS3003) | 0x44 | `ModulinoThermo` |
| **Modulino Touch** | 4 capacitive touch pads | 0x5A | `ModulinoTouch` |

## Canonical sketch — read a Modulino

```cpp
#include <Modulino.h>

ModulinoDistance distance;

void setup() {
    Serial.begin(115200);
    Modulino.begin();        // initializes Wire on I²C4
    distance.begin();
}

void loop() {
    if (distance.available()) {
        int mm = distance.get();
        Serial.print("Distance: ");
        Serial.print(mm);
        Serial.println(" mm");
    }
    delay(100);
}
```

## Canonical sketch — combine multiple Modulinos

You can plug several Modulinos into a Qwiic daisy-chain (each has two connectors so they pass through). The library handles multiple devices by I²C address:

```cpp
#include <Modulino.h>

ModulinoBuzzer buzzer;
ModulinoDistance distance;
ModulinoPixels pixels;

void setup() {
    Modulino.begin();
    buzzer.begin();
    distance.begin();
    pixels.begin();
}

void loop() {
    int mm = 0;
    if (distance.available()) mm = distance.get();

    if (mm > 0 && mm < 100) {
        // Object close: beep + red LEDs
        buzzer.tone(1000, 100);
        pixels.set(0, ModulinoColor(255, 0, 0));
    } else {
        pixels.set(0, ModulinoColor(0, 64, 0));
    }
    pixels.show();
    delay(50);
}
```

## Pitfalls

- **Forgetting `Modulino.begin()`.** Without it, `Wire` is not initialized for I²C4 and all Modulino reads return silence.
- **Two Modulinos at the same address.** You can't have two of the same type on the bus simultaneously (e.g., two ModulinoDistance), because both report at 0x29. Use a third-party I²C multiplexer if you need duplicates.
- **Power-hungry combo.** A full chain of Modulinos can draw 100+ mA from the Qwiic 3.3 V. The on-board 3.3 V rail has a budget — see `uno-q-hardware/references/power.md`.
- **Confusing Qwiic with the Arduino `Wire` headers on D20/D21.** Those are I²C2, a separate bus from I²C4. Modulino library targets I²C4. A regular I²C sensor on D20/D21 uses `Wire` directly without `Modulino.begin()`.

## See also

- `uno-q-hardware/references/connectors.md` — Qwiic pinout.
- `bridge/SKILL.md` — combine a Modulino reading with Python on the Linux side.
- `sketch-patterns/SKILL.md` — for general sketch scaffolding.
