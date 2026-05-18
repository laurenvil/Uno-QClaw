---
name: sketch-patterns
description: Canonical Arduino sketch templates for Uno Q — scaffold, breathing/fading LED (analogWrite for-loops), blink, button with INPUT_PULLUP, potentiometer analogRead, Servo sweep. Read this before writing any .ino sketch.
---

# Arduino Sketch Patterns (Uno Q)

A small library of canonical, compilable templates. Read the matching reference file *before* writing a sketch — do not invent variants when a template exists.

## The scaffold (every sketch)

```cpp
void setup() {
    // pinMode calls go here
}

void loop() {
    // repeating logic goes here
}
```

No statements at global scope except `#include`, `const`, and `#define`. An empty `setup()` is incomplete — every pin used with `digitalWrite`, `analogWrite`, or `analogRead` needs a matching `pinMode()` in `setup()`.

## When to load each reference

| User asks for… | Read |
|---|---|
| Fade, breathe, smooth on/off | `references/breathing.md` |
| Blink, flash, on/off at 1 Hz | `references/blink.md` |
| Button, switch, pressed | `references/button.md` |
| Potentiometer, dial, knob, Serial value | `references/potentiometer.md` |
| Servo, sweep, angle | `references/servo.md` |

## Anti-pattern reminders (covered in detail in references)

- **Breathing/fading LED uses `analogWrite` in ascending then descending for-loops.** A boolean toggle between 0 and 255 is a blink, not a fade — never confuse the two.
- **Blink uses `digitalWrite` with two `delay(1000)` calls.** One delay leaves the LED in an indeterminate state on the next loop iteration.
- **Button reads with `INPUT_PULLUP` and tests for `LOW`** (pressed pulls the line down). Floating inputs read noise.
- **Always `Serial.begin(9600)` in `setup()`** before any `Serial.print` / `Serial.println`. Otherwise the Serial Monitor sees nothing.
