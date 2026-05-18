# Button → LED

Read a momentary push button on a digital pin, light an LED while the button is held.

## Wiring assumption

The user wires one side of the button to the digital input pin and the other side to **GND**. The MCU's internal pull-up (`INPUT_PULLUP`) holds the line at 3.3 V when the button is released, and the button pulls it to 0 V when pressed. **No external resistor needed.**

## Canonical template

```cpp
const int buttonPin = 2;
const int ledPin = LED_BUILTIN;   // D13

void setup() {
    pinMode(buttonPin, INPUT_PULLUP);
    pinMode(ledPin, OUTPUT);
}

void loop() {
    if (digitalRead(buttonPin) == LOW) {   // LOW = pressed (pull-up + button-to-GND)
        digitalWrite(ledPin, HIGH);
    } else {
        digitalWrite(ledPin, LOW);
    }
}
```

## Why `LOW` means pressed

`INPUT_PULLUP` enables the internal ~40 kΩ pull-up to 3.3 V, so the pin reads **HIGH when the button is open**. Closing the button creates a path to GND, which the pull-up loses against — the pin reads **LOW**. Inverting the logic confuses many users. Call this out.

## Common variations

- **External pull-down wiring** (button to +3.3 V, pull-down resistor to GND): use `pinMode(buttonPin, INPUT)` and test `== HIGH`.
- **Toggle on press** (push to switch on, push again to switch off): track previous state, watch for the LOW→HIGH transition. This needs debounce (`millis()` or `delay(50)` after press).
- **Different LED pin:** change `ledPin` to any digital pin and wire LED + 220 Ω to that pin.

## Anti-patterns

- **Forgetting `INPUT_PULLUP`** → pin floats, `digitalRead` returns random noise, LED flickers without anyone pressing the button.
- **Testing for `HIGH` when wired with `INPUT_PULLUP`** → backwards logic, LED is on while button is *released*.
- **Long `delay()` inside `loop()`** before reading the button → input feels unresponsive. Keep the loop body short.
