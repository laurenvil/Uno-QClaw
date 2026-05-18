---
name: uno-q-hardware
description: Arduino Uno Q board pinout and voltage rules — JDIGITAL/JANALOG/Qwiic/JSPI pin tables, PWM pins, 3.3V ADC limits, MPU vs MCU split. Read this before answering any question that names a pin (D0–D21, A0–A5) or voltage.
---

# Arduino Uno Q Hardware

The Uno Q has **two processors** that talk over an RPC Bridge.

- **MPU (Linux side)** — Qualcomm QRB2210, 4× Cortex-A53 @ 2.0 GHz, Debian Linux. Runs Python, AI inference, web servers. MPU I/O is 1.8 V and **not** accessible from Arduino sketches.
- **MCU (Arduino side)** — STM32U585, Cortex-M33 @ 160 MHz, Zephyr OS + Arduino Core. Runs `.ino` sketches. **All Arduino headers (JDIGITAL, JANALOG, JSPI, Qwiic) are 3.3 V.**

Sketches always target the MCU. The MPU is where QClaw itself runs.

## When to load the references

- User asks about a specific pin (D-number, A-number) → read `references/pinout.md`.
- User asks about voltage, 5 V sensors, ADC range, or "is it safe" → read `references/voltage-safety.md`.
- Writing any sketch that uses `analogWrite`, `analogRead`, I2C, SPI, or Serial → check `references/pinout.md` for the pin's role first.

## Quick facts (use without loading references)

- PWM pins: **D3, D5, D6, D9, D10, D11** (marked with `~` on the silkscreen).
- Built-in LED: **D13**.
- I2C2 (default Wire): **D20 (SDA), D21 (SCL)**.
- Qwiic connector: dedicated I2C4, plug-and-play for Modulino sensors.
- ADC inputs A0–A5: **0–3.3 V only**. 5 V on these pins damages the MCU — call this out every time.

## Reference files

| File | Contents |
|---|---|
| `references/pinout.md` | Full JDIGITAL / JANALOG / Qwiic / JSPI tables — pin, MCU port, and alternate function. |
| `references/voltage-safety.md` | 3.3 V vs 5 V rules, MPU↔MCU I/O split, common ways users damage the board. |
