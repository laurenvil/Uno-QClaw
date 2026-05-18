# STM32U585 Op-Amps on the Uno Q

The STM32U585 has integrated programmable op-amps. Two of them are exposed on the standard headers:

| Op-amp | Inputs | Output | Available where |
|---|---|---|---|
| **OPAMP1** | INP / INM on JMISC pins 22 / 24 | VOUT on JMISC pin 20 | JMISC carrier-board only |
| **OPAMP2** | INPUT+ on A2 (PA6), INPUT− on A3 (PA7) | OUTPUT on ~D3 (PB0) | JANALOG + JDIGITAL — accessible on any standard breadboard setup |

**OPAMP2 is the one most user projects will use** because it sits on user-accessible pins. The rest of this reference focuses on OPAMP2.

## Why on-chip op-amps matter

You can buffer / amplify / level-shift an analog signal without a separate IC. The Arduino API doesn't expose op-amp configuration directly; use the STM32 HAL (`HAL_OPAMP_Init`, `HAL_OPAMP_Start`) from a sketch.

Common use cases:

| Use case | Configuration |
|---|---|
| **Voltage follower** (unity-gain buffer) | Follower mode — output = input. Buffers a high-impedance sensor before the ADC. |
| **Non-inverting amplifier** | Programmable gain × 2 / × 4 / × 8 / × 16. Amplifies a weak sensor signal. |
| **External op-amp** | INP and INM both come from external pins. Build any topology with external resistors. |

## Canonical sketch — OPAMP2 as a voltage follower

This buffers a high-impedance source (a 10 MΩ photodiode, say) connected to A2 and outputs a low-impedance copy on D3 that the ADC or downstream circuitry can read cleanly.

```cpp
#include "stm32u5xx_hal.h"

OPAMP_HandleTypeDef hopamp2;

void setup() {
    // Enable the OPAMP peripheral clock
    __HAL_RCC_OPAMP_CLK_ENABLE();

    hopamp2.Instance = OPAMP2;
    hopamp2.Init.PowerMode        = OPAMP_POWERMODE_NORMAL;
    hopamp2.Init.Mode             = OPAMP_FOLLOWER_MODE;
    hopamp2.Init.NonInvertingInput = OPAMP_NONINVERTINGINPUT_IO0;   // PA6 / A2
    hopamp2.Init.PowerSupplyRange = OPAMP_POWERSUPPLY_HIGH;
    HAL_OPAMP_Init(&hopamp2);
    HAL_OPAMP_Start(&hopamp2);

    // OPAMP2 output is on PA3 internally, but the Uno Q routes it to PB0 (D3).
    // No pinMode() needed for the analog output.
}

void loop() {
    // Read the buffered signal back through ADC on A2 (or directly on D3 if wired).
    int v = analogRead(A2);
    Serial.println(v);
    delay(100);
}
```

## Canonical sketch — non-inverting × 4 amplifier

Useful when a sensor outputs 0–0.8 V and you want to use the full 0–3.3 V ADC range:

```cpp
#include "stm32u5xx_hal.h"

OPAMP_HandleTypeDef hopamp2;

void setup() {
    __HAL_RCC_OPAMP_CLK_ENABLE();
    hopamp2.Instance = OPAMP2;
    hopamp2.Init.PowerMode         = OPAMP_POWERMODE_NORMAL;
    hopamp2.Init.Mode              = OPAMP_PGA_MODE;
    hopamp2.Init.PgaGain           = OPAMP_PGA_GAIN_4;            // ×4
    hopamp2.Init.NonInvertingInput = OPAMP_NONINVERTINGINPUT_IO0; // PA6 / A2
    hopamp2.Init.PowerSupplyRange  = OPAMP_POWERSUPPLY_HIGH;
    HAL_OPAMP_Init(&hopamp2);
    HAL_OPAMP_Start(&hopamp2);
}

void loop() {
    int v = analogRead(A2);
    Serial.println(v);
    delay(100);
}
```

`OPAMP_PGA_GAIN_2`, `_4`, `_8`, `_16` are all available. Output saturates at the 0–3.3 V rail.

## Pitfalls

- **Forgetting to enable the clock.** `__HAL_RCC_OPAMP_CLK_ENABLE()` must run before `HAL_OPAMP_Init`. Otherwise the configuration silently fails.
- **Output saturates near the rails.** OPAMP2 has rail-to-rail output but only to within ~50 mV. Plan for 0.05 V – 3.25 V usable range, not 0 – 3.3 V exactly.
- **High-impedance source on the inverting input.** PGA mode internally connects the inverting input to a divider — don't drive PA7 externally when in PGA mode.
- **Confusing OPAMP2_OUTPUT with PWM on D3.** D3 (PB0) is also a PWM pin (TIM3_CH3). When OPAMP2 is started, the pin is in analog output mode; `analogWrite()` PWM on D3 will not work simultaneously.
- **Power supply mode.** Use `OPAMP_POWERSUPPLY_HIGH` for 3.3 V operation. Wrong mode degrades bandwidth and offset.

## See also

- `dac.md` — buffer the DAC output through OPAMP2 to drive heavier loads.
- `potentiometer.md` — combine an op-amp buffer with analogRead for a high-impedance sensor.
- `uno-q-hardware/references/pinout.md` — confirms OPAMP2 inputs/output pins.
