# Bridge — MCU side (Arduino sketch / STM32U585)

The MCU sketch exposes services that Python on the Linux side can call by name, and pushes notifications for asynchronous events.

## Skeleton — expose a service

```cpp
#include <Arduino.h>
#include <Bridge.h>

void setup() {
    Bridge.begin();   // must be called before any Bridge usage

    // Register a service the Python side can call
    Bridge.on("read_a0", []() -> int {
        return analogRead(A0);
    });
}

void loop() {
    Bridge.poll();    // service Bridge messages; required in loop()
}
```

`Bridge.on(name, handler)` registers a named service. The handler runs when the Python side calls `bridge.call(name)`. Return value is serialised back to the caller.

## Service with arguments

```cpp
Bridge.on("set_led", [](int pin, int brightness) {
    pinMode(pin, OUTPUT);
    analogWrite(pin, brightness);
});
```

Python side:

```python
bridge.call("set_led", pin=13, brightness=128)
```

Argument names match between sides. Types are encoded automatically (`int`, `float`, `bool`, `String`, structs).

## Service returning a struct

```cpp
struct ImuReading { float x, y, z; };

Bridge.on("read_imu", []() -> ImuReading {
    ImuReading r;
    r.x = read_accel_x();
    r.y = read_accel_y();
    r.z = read_accel_z();
    return r;
});
```

Python side receives a dict: `{"x": ..., "y": ..., "z": ...}`.

## Push a notification (one-way event)

```cpp
const int BUTTON_PIN = 2;
int lastState = HIGH;

void setup() {
    Bridge.begin();
    pinMode(BUTTON_PIN, INPUT_PULLUP);
}

void loop() {
    int now = digitalRead(BUTTON_PIN);
    if (now == LOW && lastState == HIGH) {
        // Press detected — notify Linux
        Bridge.notify("button_pressed", BUTTON_PIN);
    }
    lastState = now;
    Bridge.poll();
    delay(20);   // crude debounce
}
```

Python side:

```python
bridge.subscribe("button_pressed", lambda pin: print(f"pressed pin {pin}"))
bridge.run_forever()
```

## Logging from MCU through Bridge

```cpp
Bridge.log("sensor calibration starting");
```

Appears in App Lab's Sketch console.

## Common patterns

### Pattern 1 — sensor service

```cpp
#include <Arduino.h>
#include <Bridge.h>

void setup() {
    Bridge.begin();
    Bridge.on("read_a0", []() -> int { return analogRead(A0); });
}

void loop() { Bridge.poll(); }
```

### Pattern 2 — actuator with bounds check

```cpp
#include <Arduino.h>
#include <Bridge.h>
#include <Servo.h>

Servo myServo;

void setup() {
    Bridge.begin();
    myServo.attach(9);
    Bridge.on("set_servo", [](int angle) -> bool {
        if (angle < 0 || angle > 180) return false;
        myServo.write(angle);
        return true;
    });
}

void loop() { Bridge.poll(); }
```

### Pattern 3 — event-driven notify

See the button example above.

## Pitfalls

- **Forgetting `Bridge.poll()` in `loop()`.** Without it, services never fire, notifications never send.
- **Long-running handlers block the loop.** Bridge calls run inline. If a handler takes 500 ms, `loop()` is stuck for 500 ms. Use notifications for asynchronous work.
- **Using `Serial.print` for debugging while Bridge runs over USB CDC.** They share the transport. Use `Bridge.log(...)` instead — it goes through the framed channel and shows up in App Lab.
- **Returning before all argument validation.** Always validate parameter ranges and return a typed error/bool rather than crashing.

## See also

- `python-side.md` for the Python counterpart to every example here.
- `examples.md` for three full projects (sensor relay, AI-controlled LED, button → web request).
