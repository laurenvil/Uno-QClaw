# DAC outputs on the Uno Q (A0 / A1)

The STM32U585 has two 12-bit DACs (DAC0 and DAC1) wired to **A0 (PA4)** and **A1 (PA5)** on the JANALOG header. These produce real analog voltage on the pin — unlike `analogWrite()` which is PWM. Use them for audio tones, function generators, control voltages, AM modulation.

| Pin | DAC channel | Range | Resolution |
|---|---|---|---|
| A0 (PA4) | DAC1 channel 1 | 0 – 3.3 V | 12-bit (0–4095) |
| A1 (PA5) | DAC1 channel 2 | 0 – 3.3 V | 12-bit (0–4095) |

**Note:** `analogWrite()` on A0/A1 maps the 0–255 value to the 12-bit DAC and produces a real analog voltage, not PWM. This is different from `analogWrite()` on D3/D5/D6/D9/D10/D11 which produces PWM via the timer peripheral.

## Canonical sketch — output a steady voltage

```cpp
void setup() {
    // A0 / A1 do not need pinMode() before analogWrite when used as DAC
}

void loop() {
    // 0.5 × 3.3 V = 1.65 V on A0
    analogWrite(A0, 128);   // 128 / 255 ≈ 0.5
    delay(1000);

    // 0 V on A0
    analogWrite(A0, 0);
    delay(1000);
}
```

## Canonical sketch — generate a sine wave (440 Hz, A4 musical note)

```cpp
#include <math.h>

const float FREQ_HZ = 440.0;
const int SAMPLES = 100;
int waveform[SAMPLES];

void setup() {
    // Pre-compute one cycle of a sine wave (12-bit, 0..4095)
    for (int i = 0; i < SAMPLES; i++) {
        float t = (float)i / SAMPLES;
        float v = (sin(2.0 * M_PI * t) + 1.0) * 0.5;   // 0..1
        waveform[i] = (int)(v * 4095.0);
    }
}

void loop() {
    static unsigned long lastUs = 0;
    static int index = 0;
    unsigned long periodUs = (unsigned long)(1000000.0 / (FREQ_HZ * SAMPLES));

    unsigned long now = micros();
    if (now - lastUs >= periodUs) {
        lastUs = now;
        // analogWriteResolution(12) lets us pass 0..4095 directly to the DAC.
        // If not called, the default is 8-bit (0..255) and the DAC scales accordingly.
        analogWriteResolution(12);
        analogWrite(A0, waveform[index]);
        index = (index + 1) % SAMPLES;
    }
}
```

Wire A0 through a small RC low-pass filter (e.g. 1 kΩ + 100 nF) to smooth the steps, then into a piezo speaker or audio amplifier.

## Canonical sketch — control voltage for analog circuitry

```cpp
// Output a slow ramp from 0 V to 3.3 V over 5 seconds, then repeat.
void setup() {
    analogWriteResolution(12);
}

void loop() {
    for (int v = 0; v <= 4095; v++) {
        analogWrite(A0, v);
        delayMicroseconds(1200);   // ~5 s total
    }
}
```

## When NOT to use the DAC

- **Driving a 4–8 Ω speaker directly.** The DAC source impedance is too high. Use an audio amplifier in between.
- **Anything above ~50 kHz.** The DAC settling time and the `loop()` timing aren't fast enough for higher frequencies. Use a DDS chip or a different MCU.
- **High output current.** The DAC outputs are not rated for current drive. Buffer through a unity-gain op-amp for any load that draws more than a few mA.

## Pitfalls

- **Forgetting `analogWriteResolution(12)`.** Default is 8-bit on most Arduino cores. With the default, you write 0–255 and the DAC scales to 0–4095, losing 4 bits of resolution.
- **Stepped output instead of smooth.** That's inherent to the DAC — the output is a series of voltage levels held for the sample period. Use an RC filter to smooth.
- **Loading the DAC output.** Anything above a few mA load (LEDs, motors) collapses the output voltage. Buffer through an op-amp.
- **Conflict with ADC.** A0 and A1 are also `analogRead()` inputs. You can't read and write the same pin at the same time — pick one role per pin.

## See also

- `uno-q-hardware/references/pinout.md` — confirms DAC0 on A0 and DAC1 on A1.
- `opamp.md` — buffer the DAC through an op-amp for higher current.
- `breathing.md` — uses `analogWrite()` PWM on D9; same function call but very different physical output.
