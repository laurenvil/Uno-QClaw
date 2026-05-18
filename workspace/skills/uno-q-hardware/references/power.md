# Powering the Uno Q

The Uno Q accepts power from one of three inputs. Pick the one that matches your deployment.

## The three inputs

| Input | Connector | Voltage range | Max current | When to use |
|---|---|---|---|---|
| **USB-C VBUS** | USB-C port (JUSB1) | 5 V (PD 5V/3A profile) | 3 A | Bench-top development, programming via App Lab, USB host/display for SBC mode |
| **VIN (DC IN)** | JANALOG pin 8 (or JMEDIA) | 7–24 V | — | Robotics, battery packs, vehicle power, deployment carts |
| **5V pin** | JANALOG pin 5 | 5 V regulated | 3 A | When you already have a clean regulated 5 V supply nearby |

Apply power to **one** of the three. Combining USB and VIN works (they're diode-OR'd onto the system 5V bus) but the USB will not power your VIN-side regulators if VIN is higher.

## Power Delivery details

**USB-C VBUS** requests the **5 V / 3 A profile** only. The Uno Q does NOT request 9 V / 12 V / 15 V / 20 V profiles. Use a USB-C source and cable rated for at least 5 V at 3 A — undersized supplies cause brown-outs during Wi-Fi bursts or display initialization.

**Reverse-polarity protection** on VIN is verified to −24 V. Don't deliberately apply reverse voltage; protection means a wiring mistake won't destroy the board, not that reverse voltage is operational.

## On-board voltage rails (derived from the input)

| Rail | Voltage | Origin | Used by |
|---|---|---|---|
| **5V_SYS** | 5.0 V | Diode-OR of USB-C VBUS and 7–24 V buck output | System bus; powers PMIC and main rails |
| **PWR_3P8V** | 3.8 V | Step-down buck from 5V_SYS | Reserved for system design (LTE/cellular if added) |
| **PWR_3P3V** | 3.3 V | Step-down buck from PWR_3P8V | STM32U585, ANX7625 DP bridge, Wi-Fi 3.3 V domain, **all 3.3 V header pins** |
| **VREG_L15A_1P8V** | 1.8 V | PM4125 PMIC LDO from 5V_SYS | MPU SoC I/O banks, ANX DVDD18, Wi-Fi digital, level shifters, JMISC 1.8 V section |

The 3.3 V rail powers everything users see on the headers. If the 3.3 V rail sags (undersized USB supply, badly seated power cable), every analog read drifts and digital outputs can glitch.

## Recommended operating conditions

| Parameter | Min | Typical | Max | Unit |
|---|---|---|---|---|
| USB-C input (VBUS_USBC) | 4.5 | 5.0 | 5.5 | V |
| DC input (DC_IN, VIN) | 7.0 | — | 24.0 | V |
| 3.3 V system rail (PWR_3P3V) | 3.1 | 3.3 | 3.5 | V |
| Operating temperature (T_OP) | −10 | — | 60 | °C |

Brief dips below the minimum cause resets or link drops. Stay comfortably above minimum, especially at the upper end of T_OP (the QRB2210 throttles above 60 °C ambient).

## Output power available on headers

| Pin | Header | Voltage | Max drain |
|---|---|---|---|
| **3V3 OUT** | JANALOG (×2), JMISC, Qwiic | 3.3 V | ~500 mA total (shared) |
| **+5V_USB OUT** | JANALOG, JMISC | 5 V | Limited by USB-C contract (3 A total minus board draw) |
| **VIN** | JANALOG pin 8, JMEDIA | 7–24 V passthrough | — |
| **+1V8 (OUT)** | JCTL, JMISC | 1.8 V reference | <50 mA; reference only — don't sink current |

Power-hungry peripherals (motors, big servos, LCD backlights) should NOT be powered from the on-board rails. Use a separate supply rated for the load and share only ground with the Uno Q.

## Powering motors and servos

A servo at idle draws ~10–30 mA. Stall current can hit 1 A. Multiple servos on the on-board 5 V rail will brown out the Uno Q.

**Right way:** separate 5 V (or 6 V) supply for the servo, common ground with the Uno Q, control wire from a PWM pin (D3, D5, D6, D9, D10, D11). Use a Servo library; pulses are 1 ms–2 ms within a 20 ms period.

**Wrong way:** plugging multiple servos directly into 5V pin → 3.3 V rail droops → A0 readings jump around → user blames the code.

## Pitfalls

- **Tablet chargers labeled "5V 1A".** Underpowered. Use a 5 V / 3 A USB-C supply.
- **VIN with positive on the wrong terminal.** Even with reverse-polarity protection, don't rely on it as a feature.
- **Hot-plugging USB while VIN is active.** The diode-OR handles it electrically, but USB host devices on the board can disconnect briefly. Power down before swapping sources for deployment demos.
- **Long thin USB cables.** Voltage drop across a 2 m cheap cable can drop VBUS from 5.0 V to 4.6 V at full load. Use short, thicker cables for stable operation.
- **Powering through the 5V pin while USB-C is also plugged in.** Both sources hit 5V_SYS through Schottky diodes; whichever is higher wins. Pick one source per session.

## Diagnostics

| Symptom | Likely cause |
|---|---|
| Board boots, then resets ~30 s in | Power supply can't sustain Wi-Fi turn-on (~600 mA spike). Use a 3 A USB-C supply. |
| Random USB drops during heavy CPU load | Cable voltage drop. Try a different cable. |
| A0 readings drift up and down with no input change | 3.3 V rail sagging. Check supply. |
| MCU reset on motor stall | Motor sharing the on-board 5 V rail. Move it to a separate supply. |
| Hot to the touch | Normal under heavy load (CPU + GPU + Wi-Fi); concerning if ambient is also high. Check T_OP. |

## See also

- `connectors.md` — which pin is which input.
- `voltage-safety.md` — what voltages each pin tolerates.
