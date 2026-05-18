# Bricks — Modular building blocks for App Lab Apps

A **Brick** is a pre-packaged Linux-side service that drops into an App Lab project. Bricks encapsulate common building blocks so a user doesn't have to write the underlying infrastructure.

## Typical Bricks

| Brick type | What it provides |
|---|---|
| **AI Model** | Pre-trained model + inference wrapper (object detection, speech recognition, keyword spotting) |
| **Web UI** | A web server serving a dashboard, dropped into the App as a route + assets |
| **REST API Client** | Pre-configured connector to an external service (weather, MQTT broker, IFTTT) |
| **Database** | Embedded SQLite or a small key-value store accessible from `main.py` |
| **Sensor Library** | Higher-level Python wrappers for common Modulino / I²C devices via Bridge |

Bricks run **on the Linux MPU side**, alongside `main.py`. They are managed by App Lab and started automatically when the App runs.

## Using a Brick in your App

The exact import name and API depend on the specific Brick. The general pattern:

```python
# main.py
from arduino import Bridge
from bricks.object_detection import ObjectDetector

bridge = Bridge(); bridge.begin()
detector = ObjectDetector()
detector.start()

def on_frame(frame):
    results = detector.predict(frame)
    if results.has_class("person"):
        bridge.call("turn_on_light")

# detector emits frames on its own thread; on_frame is called for each.
detector.on_frame(on_frame)

import time
while True: time.sleep(1)
```

The MCU sketch exposes `turn_on_light` (see `bridge/references/mcu-side.md`).

## Where Bricks live

In App Lab, Bricks are added through the **"Select Brick"** dialog when configuring an App. They are downloaded from Arduino's catalog and installed into the App's `bricks/` directory.

You can also write your own Brick — it's just a Python package that follows the Brick interface (a `start()` method, a `stop()` method, and a way for Python code to consume its output).

## When to use a Brick vs writing it yourself

| | Use a Brick | Write it yourself |
|---|---|---|
| AI inference (vision, speech) | ✅ — the heavy lifting is done | If the existing Brick doesn't match your model |
| Simple HTTP fetch | ❌ overkill | ✅ — `requests.get()` is one line |
| Web dashboard | ✅ if a relevant one exists | If your UI is custom enough to warrant Flask/FastAPI |
| Bridge integration | The Brick API handles it | Direct `bridge.call()` if simpler |

## QClaw and Bricks

QClaw does NOT install or manage Bricks. QClaw writes sketches and Python code; App Lab is where Bricks are added.

What QClaw *can* do is generate code that **uses** a Brick once it's been installed in your App. The skill content available to QClaw includes patterns for the standard Brick APIs.

## Pitfalls

- **Forgetting to register the Brick in your App configuration.** The Brick won't start, your `import bricks.foo` will fail.
- **Bricks that require Wi-Fi failing silently when offline.** AI Brick downloads, weather Bricks, etc. need network. Test offline behavior explicitly.
- **Heavy-weight Bricks on the 2 GB Uno Q variant.** Some AI Bricks need ~600 MB of RAM. On the 2 GB board, RAM gets tight if you also run `llama-server` for QClaw. Prefer the 4 GB variant for production AI projects.

## See also

- `deploy.md` for the full App lifecycle.
- `bridge/SKILL.md` because every non-trivial Brick interacts with the MCU through Bridge.
