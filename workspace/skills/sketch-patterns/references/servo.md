# Servo Sweep

Drive a hobby servo (SG90, MG90S, etc.) using the standard `Servo` library. Sweep from 0° to 180° and back.

## Wiring assumption

Three-wire servo cable:
- Red (Vcc) → **+5 V** header pin (most hobby servos need 5 V; they will under-perform or stall on 3.3 V).
- Brown / black (GND) → **GND**.
- Orange / yellow (signal) → any digital pin (D9 is conventional). The signal is 3.3 V PWM, which most 5 V servos accept on their input line.

⚠ A servo's stall current can dip the rail and reset the board. For more than one servo, power servos from a separate 5 V supply with shared GND.

## Canonical template

```cpp
#include <Servo.h>

Servo myServo;
const int servoPin = 9;

void setup() {
    myServo.attach(servoPin);
}

void loop() {
    for (int angle = 0; angle <= 180; angle++) {
        myServo.write(angle);
        delay(15);
    }
    for (int angle = 180; angle >= 0; angle--) {
        myServo.write(angle);
        delay(15);
    }
}
```

## Why this works

- `myServo.attach(pin)` claims the pin for servo-pulse output (50 Hz PWM with 1–2 ms pulse widths).
- `myServo.write(angle)` sets target angle 0–180°.
- `delay(15)` gives the servo time to physically reach each step. Below ~10 ms it cannot keep up.

## Common variations

- **Single move**, not sweep: drop the `for` loops, call `myServo.write(90);` once in `setup()`.
- **Read pot → drive servo:** `int v = analogRead(A0); int a = map(v, 0, 1023, 0, 180); myServo.write(a);` inside `loop()`.
- **Continuous-rotation servo:** writes are *speeds* (90 = stop, 0 = full reverse, 180 = full forward) — not angles. Different code, same library.

## Anti-patterns

- **Powering the servo from 3.3 V** → twitchy, weak movement, or no movement at all.
- **Missing `#include <Servo.h>`** → `Servo` undeclared error.
- **No `attach()` call** → `write()` is silently ignored.
- **Calling `attach()` inside `loop()`** → re-initializes the pin on every iteration, glitches the servo.
