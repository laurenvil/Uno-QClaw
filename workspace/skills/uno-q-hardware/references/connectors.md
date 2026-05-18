# Uno Q — Connectors and Headers at a glance

The Uno Q exposes seven user-facing connectors. Each operates in a specific voltage domain and is owned by either the MPU (Linux side, 1.8 V) or the MCU (Arduino side, 3.3 V).

## The seven connectors

| Connector | Designator | Pins | Domain | Owner | Used for |
|---|---|---|---|---|---|
| **JDIGITAL** | A2 | 18 | 3.3 V | MCU | Arduino digital I/O headers — D0–D13, D20, D21, AREF, GND. SPI/I²C/UART/CAN/PWM. The "Arduino" header in the classic sense. |
| **JANALOG** | A3 | 14 | 3.3 V (analog) | MCU | Analog inputs A0–A5, power pins (3V3 OUT, 5V USB VBUS, VIN 7–24 V, GND), BOOT/IOREF/RESET. |
| **JSPI** | A5 | 6 | 3.3 V | MCU | Dedicated SPI header (MISO/MOSI/SCK + 5V + RESET + GND) — for SPI peripherals that need a clean dedicated bus. |
| **Qwiic** | A4 | 4 | 3.3 V | MCU | Plug-and-play I²C4 connector (GND, 3V3, SDA, SCL) for Modulino sensors and Sparkfun Qwiic ecosystem. |
| **JCTL** | A1 | 10 | 1.8 V | MPU | Boot/reset/console: USB_BOOT, VOL_UP, VOL_DOWN, SE4 UART console TX/RX, PMIC_RESET, VBUS_DISABLE, +1V8. **Not** for user GPIO — system functions only. |
| **JMISC** | B1 | 60 | mixed 1.8 V / 3.3 V | both | Advanced expansion. Carries 3.3 V MCU pins (PSSI parallel camera, SDMMC1, TRACE, I²C4, MCO, OPAMP1, GPIO) AND 1.8 V MPU pins (SoC GPIOs SE0 bank, audio endpoints). |
| **JMEDIA** | B2 | 60 | 1.8 V (D-PHY) | MPU | 4-lane MIPI-CSI-2 camera + 4-lane MIPI-DSI display. Carrier-board only — these are differential pairs, not GPIO. |

## Header use guide

### "I want to plug in a sensor / breadboard"

→ **JDIGITAL** (D0–D13, D20, D21) for digital, **JANALOG** (A0–A5) for analog. Both 3.3 V. Standard Arduino UNO header pitch — most UNO shields fit.

### "I have a Qwiic-style sensor module"

→ **Qwiic** connector. Plugs in directly, no breadboard or soldering. Sketch uses `Wire.h` to talk to it (this is I²C4, separate from the `Wire` instance which is I²C2 on D20/D21).

### "I want to add an SPI display or SD card"

→ **JSPI** for a dedicated bus, or **D10–D13** on JDIGITAL for the shared SPI2 (which conflicts with using D10–D13 as GPIO).

### "I want to plug in a camera"

→ **JMEDIA** — but only through a carrier board with the right MIPI-CSI-2 flex connector. You can't just wire a camera to header pins; this is a 4-lane differential bus that requires impedance-controlled traces.

### "I want to connect a USB keyboard / mouse / camera"

→ **USB-C port** in SBC mode. The Uno Q's USB-C supports role switching (host or device) and includes DisplayPort Alt-Mode for video output. Use a USB-C dongle if you need both power and USB host simultaneously.

### "I want to wire a button or LED to a system-controlled GPIO from Linux"

→ Linux owns the SE0 bank on **JMISC** (1.8 V) and the JCTL GPIOs (1.8 V). These can be driven via `/sys/class/gpio` or `libgpiod`. Note the **1.8 V level** — you almost always need a level shifter if you're connecting a 3.3 V or 5 V external component. Most user projects should drive headers from the MCU instead, where 3.3 V is native.

### "I want to drive an HDMI monitor"

→ The USB-C port supports DisplayPort Alt-Mode via the on-board ANX7625 DSI-to-DP bridge. Use a USB-C-to-HDMI adapter and Linux drives the display in SBC mode. Optimal resolution is 1280 × 720; supports up to 1920 × 1080.

## Voltage domain map

```
1.8 V  ─►  MPU SoC GPIO    │  JCTL (boot/console)
           Audio analog    │  JMEDIA (MIPI lanes)
           SE0 bank        │  JMISC (MPU portion)
                           │
3.3 V  ─►  MCU GPIO        │  JDIGITAL
           MCU analog      │  JANALOG (A0–A5)
           MCU SPI/I²C     │  JSPI, Qwiic
                           │  JMISC (MCU portion: PSSI, SDMMC1, TRACE, I²C4, OPAMP1)
                           │
5 V    ─►  Bus power only  │  +5V_USB on JANALOG and JSPI (drive sensors that need 5 V power
                           │   with their data lines at 3.3 V)
                           │
7–24 V ─►  Raw input       │  VIN on JANALOG, JMEDIA
```

The MCU pins on the standard headers are **3.3 V**. None of them are 5 V-tolerant in analog mode; some are 5 V-tolerant in digital input mode (the FT-type pins on JSPI specifically). Always check `voltage-safety.md` before wiring a 5 V signal to any pin.

## Pitfalls

- **Wiring a 5 V sensor signal to A0–A5.** Will damage the STM32U585 ADC. Use a voltage divider or a 3.3 V version of the sensor. See `voltage-safety.md`.
- **Trying to control JDIGITAL pins from Python.** Linux doesn't own them. Use Bridge to call the MCU.
- **Trying to control JCTL/JMISC SoC GPIOs from a sketch.** MCU doesn't own them; they're MPU pins. Use Linux GPIO from Python.
- **Plugging a 3.3 V or 5 V signal into a JCTL pin.** JCTL is 1.8 V. You will damage the QRB2210.
- **Using JMEDIA as breakout header.** Don't. MIPI lanes are differential, impedance-controlled, and reserved by Linux device tree.

## See also

- `pinout.md` — pin-by-pin reference for JDIGITAL and JANALOG.
- `voltage-safety.md` — what tolerates what, and what damages what.
- `power.md` — the power inputs and the on-board voltage rails.
