# Bridge — Python side (MPU / Linux)

Python on the Linux side of the Uno Q uses the `arduino` Bridge client to call services exposed by the MCU sketch, or to receive notifications it pushed.

## Skeleton — call an MCU service from Python

```python
# main.py — runs on the Qualcomm QRB2210 Linux MPU
from arduino import Bridge

bridge = Bridge()      # opens the default transport (USB CDC)
bridge.begin()

# Call a service the sketch exposed
value = bridge.call("read_a0")
print(f"A0 reads: {value}")
```

The string `"read_a0"` is the service name registered by `Bridge.on("read_a0", ...)` on the MCU side. Calls are type-safe — arguments and return values are encoded automatically.

## Pass arguments and read structured returns

```python
# Call a parameterised service
bridge.call("set_led", pin=13, brightness=128)

# Service that returns multiple fields
result = bridge.call("read_imu")
print(result["x"], result["y"], result["z"])
```

## Receive notifications (one-way events from the MCU)

```python
def on_button_press(payload):
    print(f"Button pressed on pin {payload['pin']}")

bridge.subscribe("button_pressed", on_button_press)

# Run the event loop
bridge.run_forever()
```

`run_forever()` blocks; notifications fire on the callback. If your Python program also needs to do other work, launch it in a thread or use `bridge.poll()` in your own loop.

## Logging from Python through Bridge

```python
bridge.log("starting inference")     # appears in App Lab's Sketch tab too
```

## Errors

`bridge.call()` raises `BridgeError` on transport failure or if the MCU returns an error. Always handle:

```python
try:
    value = bridge.call("read_a0")
except BridgeError as e:
    print(f"MCU call failed: {e}")
```

## Common patterns

### Pattern 1 — periodic sensor poll

```python
import time
from arduino import Bridge

bridge = Bridge(); bridge.begin()

while True:
    v = bridge.call("read_a0")
    print(f"A0: {v}")
    time.sleep(0.1)
```

### Pattern 2 — AI-driven actuator

```python
import time
from arduino import Bridge
import some_ai_model  # e.g. a Brick

bridge = Bridge(); bridge.begin()
model = some_ai_model.load()

while True:
    sensor = bridge.call("read_distance")
    decision = model.predict(sensor)
    bridge.call("set_servo", angle=decision)
    time.sleep(0.05)  # 20 Hz control loop
```

### Pattern 3 — push button → trigger web request

```python
import requests
from arduino import Bridge

bridge = Bridge(); bridge.begin()

def on_press(payload):
    print(f"Button {payload['pin']} pressed")
    r = requests.get("https://api.example.com/notify")
    bridge.log(f"notified, status {r.status_code}")

bridge.subscribe("button_pressed", on_press)
bridge.run_forever()
```

## See also

- `mcu-side.md` for the sketch counterpart to all of these.
- `examples.md` for three complete projects that work end-to-end.
