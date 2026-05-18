# Blink

The "hello world" of Arduino. Turn the LED on, wait, turn it off, wait, repeat. Pin D13 is the built-in LED (constant `LED_BUILTIN`).

## Canonical template

```cpp
const int ledPin = LED_BUILTIN;  // D13

void setup() {
    pinMode(ledPin, OUTPUT);
}

void loop() {
    digitalWrite(ledPin, HIGH);
    delay(1000);
    digitalWrite(ledPin, LOW);
    delay(1000);
}
```

## Why this works

- `digitalWrite(pin, HIGH)` drives the pin to 3.3 V (LED on).
- `digitalWrite(pin, LOW)` drives the pin to 0 V (LED off).
- Both `delay(1000)` calls are required — one for the on phase, one for the off phase. Together they give a 2-second cycle = 0.5 Hz blink (one blink per second).

## Common variations

- **Faster blink:** drop both delays to `delay(100)` → 10 Hz.
- **External LED on a different pin:** change `ledPin` to D2–D12 and add a 220 Ω resistor in series.
- **Non-blocking blink:** use `millis()` instead of `delay()` (advanced — only suggest if the user is past basic blink).

## Anti-patterns

- **Using `analogWrite` for blink** — analogWrite is for PWM (fade). digitalWrite is for binary on/off. They are not interchangeable.
- **Missing the second delay** — without `delay()` after `LOW`, the LED jumps straight back to `HIGH` and appears always on.
- **Forgetting `pinMode(ledPin, OUTPUT)`** — the pin defaults to high-impedance input; `digitalWrite` will not drive it.
