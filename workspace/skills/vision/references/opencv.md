# OpenCV on the Uno Q

OpenCV (Python `cv2`) is the friendliest entry point for vision projects on the MPU side. It uses V4L2 underneath; on the Uno Q the camera shows up as a standard V4L2 device.

## Install

```bash
pip install opencv-python-headless numpy
```

Use `opencv-python-headless` unless you need the `cv2.imshow()` window (which requires a connected display via USB-C DP Alt-Mode and an X server). Headless saves ~80 MB of dependencies.

## Capture a frame

```python
import cv2

cap = cv2.VideoCapture(0)
cap.set(cv2.CAP_PROP_FRAME_WIDTH, 1280)
cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 720)

ok, frame = cap.read()
if not ok:
    raise RuntimeError("camera read failed")

cv2.imwrite("snap.jpg", frame)
cap.release()
```

## Live processing loop (no display)

```python
import cv2

cap = cv2.VideoCapture(0)

try:
    while True:
        ok, frame = cap.read()
        if not ok:
            break

        # Your processing here — convert to grayscale, run a detector, etc.
        gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
        edges = cv2.Canny(gray, 100, 200)

        # Save every 30th frame so we can see progress
        # (alternative: stream over HTTP via Flask)
finally:
    cap.release()
```

## Motion detection

```python
import cv2

cap = cv2.VideoCapture(0)
subtractor = cv2.createBackgroundSubtractorMOG2(history=200, varThreshold=25)

while True:
    ok, frame = cap.read()
    if not ok:
        break

    fg_mask = subtractor.apply(frame)
    motion_pixels = cv2.countNonZero(fg_mask)
    if motion_pixels > 5000:
        print(f"motion! {motion_pixels} pixels")

cap.release()
```

## Pose via integration with Bridge → MCU

The pattern: OpenCV runs face detection on Linux; when a face is detected, Python notifies the MCU sketch which moves a servo to track it.

```python
import cv2
from arduino import Bridge

bridge = Bridge(); bridge.begin()
cap = cv2.VideoCapture(0)
face_cascade = cv2.CascadeClassifier(
    cv2.data.haarcascades + "haarcascade_frontalface_default.xml"
)

W, H = 1280, 720
cap.set(cv2.CAP_PROP_FRAME_WIDTH, W)
cap.set(cv2.CAP_PROP_FRAME_HEIGHT, H)

while True:
    ok, frame = cap.read()
    if not ok:
        break
    gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
    faces = face_cascade.detectMultiScale(gray, 1.3, 5)
    if len(faces) > 0:
        x, y, w, h = faces[0]
        cx = x + w // 2
        # Map face X position (0–W) to servo angle (0–180)
        angle = int((cx / W) * 180)
        bridge.call("set_servo_angle", angle=angle)
```

MCU sketch (with `set_servo_angle` service): see `bridge/references/mcu-side.md`.

## Use GStreamer pipeline as the source (for hardware acceleration)

`cv2.VideoCapture()` accepts a GStreamer pipeline string. This is how you get hardware-accelerated decode if your source is, say, an H.264 file:

```python
import cv2

pipeline = (
    "filesrc location=video.mp4 "
    "! qtdemux ! h264parse ! v4l2h264dec "
    "! videoconvert ! video/x-raw,format=BGR ! appsink"
)
cap = cv2.VideoCapture(pipeline, cv2.CAP_GSTREAMER)
```

Same idea for RTSP feeds:

```python
pipeline = (
    "rtspsrc location=rtsp://192.168.1.10:8554/stream "
    "! rtph264depay ! h264parse ! v4l2h264dec "
    "! videoconvert ! video/x-raw,format=BGR ! appsink"
)
cap = cv2.VideoCapture(pipeline, cv2.CAP_GSTREAMER)
```

## Pitfalls

- **First `cap.read()` returns False.** The camera may not have initialized yet. Insert `time.sleep(0.3)` between `VideoCapture()` and the first `read()`.
- **Frame rate lower than expected.** Check `cap.get(cv2.CAP_PROP_FPS)`. If the camera reports 30 fps but you see 5, the bottleneck is probably your processing loop. Profile with `time.perf_counter()`.
- **`cv2.imshow` crashes.** No X server available. Either install one (`sudo apt install xorg`) and connect a display, or drop the imshow call and save frames to disk / stream over HTTP.
- **Memory growing over time.** Old frames not being released. OpenCV's `cv2` wrappers release automatically on Python GC; this is usually a `numpy` array kept alive by your code.
- **CPU at 100% on a 720p stream.** You're using software codec instead of `v4l2h264dec`. See the GStreamer reference.

## See also

- `gstreamer.md` for hardware-accelerated pipeline construction.
- `bridge/SKILL.md` for the MCU integration pattern.
- `v4l2.md` for low-level diagnostics when `VideoCapture` doesn't work.
