# Sketch data → the network via Bridge

This is the canonical pattern for getting sensor data from an Arduino sketch on the MCU out to a remote server over Wi-Fi. The MCU has no network stack; Python on Linux has the full stack.

## The pattern

```
┌───────────────────────┐         Bridge        ┌──────────────────────┐         Wi-Fi (WCN3980)         ┌──────────────────┐
│ Arduino sketch (MCU)  │ ←———————————————————→ │ Python (Linux MPU)   │ ←———————————————————————————→  │ Remote server    │
│ reads sensor, calls   │   RPC over USB CDC    │ receives event,      │   requests / mqtt / websocket  │ (HTTP, MQTT,     │
│ Bridge.notify(...)    │                       │ does HTTP POST       │                                 │  WebSocket, …)   │
└───────────────────────┘                       └──────────────────────┘                                 └──────────────────┘
```

The MCU never sees a URL. Python never sees a pin number unless the sketch sends it.

## HTTP POST example

**MCU sketch:** read A0 every second, push the reading to Python.

```cpp
#include <Arduino.h>
#include <Bridge.h>

unsigned long lastMs = 0;

void setup() {
    Bridge.begin();
}

void loop() {
    if (millis() - lastMs >= 1000) {
        lastMs = millis();
        int reading = analogRead(A0);
        Bridge.notify("sensor_reading", reading);
    }
    Bridge.poll();
}
```

**Python:** subscribe to the notification, POST to a server.

```python
import requests
from arduino import Bridge

bridge = Bridge()
bridge.begin()

API_URL = "https://api.example.com/readings"

def on_reading(value):
    try:
        r = requests.post(API_URL, json={"a0": value}, timeout=2)
        bridge.log(f"posted, status {r.status_code}")
    except requests.RequestException as e:
        bridge.log(f"post failed: {e}")

bridge.subscribe("sensor_reading", on_reading)
print(f"Forwarding A0 readings to {API_URL}. Ctrl+C to stop.")
bridge.run_forever()
```

## MQTT example

For IoT pipelines (Home Assistant, AWS IoT, etc.), MQTT is often more natural than HTTP.

```python
# Linux side — install with: pip install paho-mqtt
import paho.mqtt.client as mqtt
from arduino import Bridge

bridge = Bridge(); bridge.begin()

mqttc = mqtt.Client()
mqttc.connect("broker.example.com", 1883)

def on_reading(value):
    mqttc.publish("unoq/a0", value)

bridge.subscribe("sensor_reading", on_reading)
mqttc.loop_start()
bridge.run_forever()
```

The MCU sketch is unchanged from the HTTP example. Decoupling protocol-from-sensor is the point.

## WebSocket / live dashboard example

For a live web dashboard, run a small server on the board itself and serve a browser page.

```python
# Linux side — install with: pip install fastapi uvicorn websockets
from fastapi import FastAPI, WebSocket
from fastapi.responses import HTMLResponse
from arduino import Bridge
import asyncio, json

bridge = Bridge(); bridge.begin()
app = FastAPI()
latest = {"a0": 0}

@app.get("/", response_class=HTMLResponse)
def index():
    return """
    <html><body><h1>Live A0</h1><div id="v">…</div>
    <script>
      const ws = new WebSocket("ws://" + location.host + "/ws");
      ws.onmessage = e => document.getElementById("v").textContent = e.data;
    </script></body></html>
    """

@app.websocket("/ws")
async def ws(socket: WebSocket):
    await socket.accept()
    while True:
        await socket.send_text(str(latest["a0"]))
        await asyncio.sleep(0.1)

bridge.subscribe("sensor_reading", lambda v: latest.update(a0=v))

if __name__ == "__main__":
    import uvicorn, threading
    threading.Thread(target=bridge.run_forever, daemon=True).start()
    uvicorn.run(app, host="0.0.0.0", port=8000)
```

Open `http://<board-ip>:8000` from any browser on the same Wi-Fi.

## Pitfalls

- **Network failures stall the MCU if you call `bridge.call()` for HTTP.** Use `Bridge.notify` from the MCU and have Python handle the HTTP timeout — that way the MCU's `loop()` is never blocked on a 5-second TCP wait.
- **Hardcoded URLs / API keys.** Put credentials in `~/.qclaw/config.json` or an `.env` file, not in the Python source.
- **Forgetting `timeout=` on `requests.get/post`.** Without a timeout, a hung server blocks Python forever.
- **Logging every reading.** `bridge.log()` on a 1 kHz sensor will saturate the USB CDC channel. Throttle or batch.

## See also

- `wifi-setup.md` for getting Linux on the network in the first place.
- `bridge/references/python-side.md` for `bridge.subscribe` / `bridge.run_forever` details.
- `bridge/references/mcu-side.md` for `Bridge.notify` details.
