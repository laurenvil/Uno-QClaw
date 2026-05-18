# Potentiometer → Serial Monitor

Read a potentiometer (or any analog sensor) on an analog input pin and print its value to the Serial Monitor.

## Wiring assumption

Three-terminal pot: one end to **3.3 V**, the other end to **GND**, the wiper (middle pin) to **A0**. ⚠ Do **not** wire to +5 V — the Uno Q's ADC tolerates 0–3.3 V only.

## Canonical template

```cpp
const int potPin = A0;

void setup() {
    Serial.begin(9600);
    // analog pins do not need pinMode for analogRead, but pinMode(potPin, INPUT) is harmless
}

void loop() {
    int value = analogRead(potPin);   // 0–1023, mapped from 0–3.3 V
    Serial.print("Pot value: ");
    Serial.println(value);
    delay(100);
}
```

## Why this works

- `analogRead(A0)` samples the wiper voltage and returns 0–1023 (12-bit ADC truncated to 10-bit for Uno API compatibility).
- `Serial.begin(9600)` opens the serial port; required for any `Serial.print*` call.
- `delay(100)` keeps the output readable (10 prints per second).

## Common variations

- **Mapping to PWM range** (drive an LED brightness from the pot): `int duty = map(value, 0, 1023, 0, 255); analogWrite(9, duty);`
- **Voltage as a float:** `float volts = value * 3.3 / 1023.0;` — note 3.3, not 5.0.
- **Faster updates:** drop `delay(100)` to `delay(20)`. Below ~10 ms the Serial Monitor cannot keep up.

## Anti-patterns

- **Missing `Serial.begin(9600)`** → Serial Monitor shows nothing. The single most common silent-failure mode.
- **Hard-coding pin `0` instead of `A0`** → reads digital pin 0 (the UART RX line). Always use the `AN` constants for analog.
- **Telling the user `1023 = 5 V`** → that is classic Uno. On Uno Q, `1023 = 3.3 V`.
