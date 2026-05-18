# Uno Q MCU Pinout (STM32U585 — 3.3 V logic)

## JDIGITAL header (A2)

| Pin | MCU | Key functions |
|-----|-----|---------------|
| D0  | PB7 | UART1 RX |
| D1  | PB6 | UART1 TX |
| D2  | PB3 | GPIO |
| ~D3 | PB0 | **PWM** (TIM2_CH2) |
| D4  | PA12 | GPIO / FDCAN1_TX |
| ~D5 | PA11 | **PWM** (TIM1) / FDCAN1_RX |
| ~D6 | PB1  | **PWM** (TIM3_CH4) |
| D7  | PB2  | GPIO |
| D8  | PB4  | SPI2 CS (Chip Select) |
| ~D9 | PB8  | **PWM** (TIM4_CH4) |
| ~D10| PB9  | **PWM** (TIM1) / SPI2 CS |
| ~D11| PB15 | **PWM** (TIM1) / SPI2 MOSI |
| D12 | PB14 | SPI2 MISO |
| D13 | PB13 | SPI2 SCK + built-in LED |
| D20 | PB11 | I2C2 SDA |
| D21 | PB10 | I2C2 SCL |

PWM-capable (`~`): **D3, D5, D6, D9, D10, D11**.

## JANALOG header (A3) — 3.3 V, NOT 5 V tolerant in ADC mode

| Pin     | MCU | Notes |
|---------|-----|-------|
| A0 / D14 | PA4 | ADC, DAC0. Max input: 3.3 V |
| A1 / D15 | PA5 | ADC, DAC1. Max input: 3.3 V |
| A2 / D16 | PA6 | ADC |
| A3 / D17 | PA7 | ADC |
| A4 / D18 | PC1 | ADC or I2C3 SDA |
| A5 / D19 | PC0 | I2C3 SCL |

⚠ **A0–A5 accept 0–3.3 V only. Do NOT connect 5 V signals.** This is different from the classic Arduino Uno (which is 5 V tolerant). 5 V on these pins permanently damages the MCU.

## Qwiic connector (A4)

I2C4 bus, PD13 (SDA) / PD12 (SCL), 3.3 V. Plug-and-play with Modulino sensors.

## JSPI header (A5)

Dedicated SPI: PC2 (MISO), PD1 (SCK), PC3 (MOSI), MCU_NRST, +5 V, GND.

## Power rails

- Header pins provide both **3.3 V** and **5 V**.
- Board input: **5 V via USB-C** or **7–24 V via VIN**.

## Arduino API summary (MCU side)

- `digitalRead`, `digitalWrite` — GPIO.
- `analogRead(pin)` — 12-bit ADC, returned as 0–1023 (mapped from 0–3.3 V).
- `analogWrite(pin, value)` — 8-bit PWM (0–255) on `~` pins only.
- `Wire` — I2C2 on D20/D21. `Wire1` for I2C3, `Wire2` for I2C4 (Qwiic).
- `SPI` — D10–D13 (SPI2) or JSPI header.
- `Servo`, `tone`, `delay`, `millis`, `micros`, `Serial`.
