# Breathing / Fading LED

A breathing LED smoothly fades in and out using PWM. Pick a `~` pin (D3, D5, D6, D9, D10, D11). D9 is the conventional default.

## Canonical template — copy exactly, change the pin number only

```cpp
const int ledPin = 9;

void setup() {
    pinMode(ledPin, OUTPUT);
}

void loop() {
    for (int i = 0; i <= 255; i++) { analogWrite(ledPin, i); delay(8); }
    for (int i = 255; i >= 0; i--) { analogWrite(ledPin, i); delay(8); }
}
```

## Why this works

- `analogWrite(pin, value)` outputs PWM at duty cycles 0 (off) through 255 (full on).
- The ascending `for` loop fades the LED in; the descending loop fades it out.
- `delay(8)` × 256 steps = ~2 seconds per fade direction → ~4 seconds per full breath.

## Common variations

- **Slower breath:** raise `delay(8)` to `delay(15)` or `delay(20)`.
- **Larger step:** change `i++` to `i += 4` and `delay(8)` to `delay(30)` — fewer, larger steps still feel smooth.
- **One-shot fade-in:** move the ascending loop to `setup()` instead of `loop()`.

## Anti-pattern — this is a BLINK, not a fade

```cpp
// WRONG — do not do this if the user asked for breathing
analogWrite(ledPin, 0);
delay(1000);
analogWrite(ledPin, 255);
delay(1000);
```

Toggling between 0 and 255 with a delay is the blink pattern. Breathing requires the `for` loop sweeping all values between.
