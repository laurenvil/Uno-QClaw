# Bridge — Three complete examples

These three projects each combine a Python program on the MPU with an Arduino sketch on the MCU, communicating via Bridge. Each example is a complete App Lab project.

---

## Example 1 — Sensor relay (Python polls MCU at 10 Hz, logs to console)

**Goal:** A potentiometer wired to A0. Python reads it through the MCU and prints the value.

**MCU sketch (`sketch.ino`):**

```cpp
#include <Arduino.h>
#include <Bridge.h>

void setup() {
    Bridge.begin();
    Bridge.on("read_a0", []() -> int {
        return analogRead(A0);
    });
}

void loop() {
    Bridge.poll();
}
```

**Python (`main.py`):**

```python
import time
from arduino import Bridge

bridge = Bridge()
bridge.begin()

print("Reading A0 at 10 Hz. Ctrl+C to stop.")
while True:
    value = bridge.call("read_a0")
    voltage = value * (3.3 / 1023.0)
    print(f"A0 = {value:4d}  ({voltage:.2f} V)")
    time.sleep(0.1)
```

**Why both sides?** The MCU owns A0. The Linux side could not read it without Bridge. The MPU has Python's richer formatting, file I/O, and network access — so logging, plotting, or upload to a server happens naturally on the Linux side.

---

## Example 2 — AI-controlled servo (Python decides, MCU actuates)

**Goal:** A distance sensor on A1. When something gets close, a servo on D9 sweeps to 90°; otherwise it rests at 0°. The "decision" is just a threshold here, but you could swap in a real ML model.

**MCU sketch:**

```cpp
#include <Arduino.h>
#include <Bridge.h>
#include <Servo.h>

Servo myServo;

void setup() {
    Bridge.begin();
    myServo.attach(9);
    myServo.write(0);

    Bridge.on("read_distance_raw", []() -> int {
        return analogRead(A1);
    });

    Bridge.on("set_servo_angle", [](int angle) -> bool {
        if (angle < 0 || angle > 180) return false;
        myServo.write(angle);
        return true;
    });
}

void loop() {
    Bridge.poll();
}
```

**Python:**

```python
import time
from arduino import Bridge

bridge = Bridge()
bridge.begin()

THRESHOLD = 600   # tune for your sensor

print("Distance-triggered servo. Ctrl+C to stop.")
while True:
    raw = bridge.call("read_distance_raw")

    # Stand-in for a real model — drop in an ML inference here later
    angle = 90 if raw > THRESHOLD else 0

    bridge.call("set_servo_angle", angle=angle)
    time.sleep(0.05)   # 20 Hz control loop
```

**Why both sides?** The MCU runs at deterministic 20 Hz with zero jitter on the servo PWM. The MPU runs the decision logic, which on real projects might be a 2 MB convolutional network — impossible on the MCU's 786 kB SRAM, easy on the MPU's 4 GB LPDDR4X.

---

## Example 3 — Button → web request (notification pattern)

**Goal:** A button on D2. When pressed, Python posts a notification to a URL. The MCU sketch never blocks waiting; it pushes a one-way Bridge notification.

**MCU sketch:**

```cpp
#include <Arduino.h>
#include <Bridge.h>

const int BUTTON_PIN = 2;
int lastState = HIGH;
unsigned long lastChangeMs = 0;
const unsigned long DEBOUNCE_MS = 30;

void setup() {
    Bridge.begin();
    pinMode(BUTTON_PIN, INPUT_PULLUP);
}

void loop() {
    int now = digitalRead(BUTTON_PIN);
    if (now != lastState && (millis() - lastChangeMs) > DEBOUNCE_MS) {
        lastChangeMs = millis();
        lastState = now;
        if (now == LOW) {
            Bridge.notify("button_pressed", BUTTON_PIN);
        }
    }
    Bridge.poll();
}
```

**Python:**

```python
import requests
from arduino import Bridge

bridge = Bridge()
bridge.begin()

def on_press(pin):
    print(f"Button on pin {pin} pressed — posting notification")
    try:
        r = requests.post(
            "https://maker.ifttt.com/trigger/uno_q_button/with/key/YOUR_KEY",
            json={"pin": pin},
            timeout=5,
        )
        bridge.log(f"HTTP {r.status_code}")
    except requests.RequestException as e:
        bridge.log(f"HTTP failed: {e}")

bridge.subscribe("button_pressed", on_press)
print("Waiting for button. Ctrl+C to stop.")
bridge.run_forever()
```

**Why both sides?** The MCU handles debounce in real time and doesn't get stuck on a 5-second HTTP timeout. The MPU has the network stack (Wi-Fi via the WCN3980 module) and the Python `requests` library — neither lives on the MCU.

---

## Choosing the pattern

| If the project is… | Use the pattern from… |
|---|---|
| Python polls the MCU on a schedule | Example 1 (call-from-Python) |
| Python decides, MCU acts continuously | Example 2 (bidirectional services) |
| MCU detects an event, Python reacts | Example 3 (notify) |

If you're combining all three, that's also fine — Bridge supports any mix of services and notifications running concurrently.
