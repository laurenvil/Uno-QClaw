---
name: vision
description: Computer vision on the Uno Q — the QRB2210 has dual ISPs (up to 25 MP at 30 fps), a 4-lane MIPI-CSI-2 camera interface on JMEDIA, and an Adreno 702 GPU with hardware H.264/H.265/VP9 codecs. Read this BEFORE writing any project that captures camera frames, runs OpenCV, decodes video, or uses GStreamer. All vision processing happens in Python on the Linux MPU side — the MCU has no camera.
---

# Computer Vision on the Uno Q

The Uno Q has hardware purpose-built for machine vision:

- **MIPI-CSI-2** — 4-lane camera interface on JMEDIA (designator B2), 1.8 V D-PHY differential pairs.
- **Dual ISPs** — 13 MP + 13 MP, or one 25 MP, at 30 fps.
- **Adreno 702 GPU** — OpenGL/Vulkan/OpenCL 2.0, hardware video codecs.
- **V4L2** — Linux exposes the camera at `/dev/video0`, `/dev/video1` and hardware codecs at `/dev/video*` (encoders/decoders).
- **GStreamer** — recommended high-level pipeline framework (`v4l2h264dec/enc`, `v4l2h265dec/enc`, `v4l2vp9dec`).

**All vision processing runs on the Linux MPU side, in Python (or C/C++).** The MCU has no camera interface. Sketches that need to "see something" call Python via Bridge.

## When to use

| Lesson scenario | Approach |
|---|---|
| Capture a still image | `gst-launch-1.0` or `cv2.VideoCapture(0)` |
| Live video preview to a USB-C HDMI monitor | GStreamer pipeline → `kmssink` or `autovideosink` |
| Detect motion in a video stream | OpenCV background subtraction |
| Run a TensorFlow Lite / PyTorch model on frames | Python + your framework of choice |
| Record an H.264 video file | GStreamer with `v4l2h264enc` (hardware encoder) |
| Decode an MP4 for playback | GStreamer with `v4l2h264dec` or `v4l2h265dec` |
| Stream video over Wi-Fi to a phone | GStreamer RTSP server |

## Quick rules

1. **MIPI cameras need a carrier board.** You cannot wire a USB webcam to JMEDIA; the 4-lane MIPI-CSI-2 is differential and impedance-controlled. Use an official Arduino Uno Q carrier board for cameras.
2. **USB webcams work too** in SBC mode. Plug into the USB-C port via a USB-C hub or dongle. They show up at `/dev/video0`.
3. **Always use V4L2-accelerated codecs** for encode/decode (`v4l2h264enc`, `v4l2h265dec`). Software fallbacks (`x264enc`, `avdec_h264`) work but burn CPU and won't keep up with 1080p30.
4. **OpenCV uses V4L2 by default** for `cv2.VideoCapture` on Linux. The CSI camera appears as a standard V4L2 device.
5. **GStreamer is the recommended pipeline** for hardware-accelerated work — the V4L2 elements are the supported interface.
6. **The MCU never sees frames.** If a sketch needs to react to vision output, Python sends a Bridge notification.

## Reference files

- `references/v4l2.md` — low-level: `/dev/video*` enumeration, `v4l2-ctl`, raw frame access.
- `references/gstreamer.md` — canonical GStreamer pipelines for capture, encode, decode, preview, RTSP streaming.
- `references/opencv.md` — Python OpenCV patterns: capture, motion detection, integration with Bridge.

## Pitfalls

- **`cv2.VideoCapture(0)` returns blank frames.** The camera may not be enumerated yet at startup. Use `v4l2-ctl --list-devices` to confirm the device exists before opening it.
- **Software codecs in GStreamer.** Using `! x264enc !` instead of `! v4l2h264enc !` will work but cost ~80% CPU and drop frames. Always prefer `v4l2*` elements.
- **Confusing CCI I²C with user I²C.** The camera control bus (CCI on JMEDIA pins 22/24, 51/53) is dedicated — don't treat it as general-purpose I²C. The MPU uses it to configure the camera sensor.
- **Trying to read MIPI lanes with a logic analyzer.** D-PHY is 1.2 V differential at >500 MHz. You can't probe it with cheap tools. Diagnose camera issues with `dmesg` and `v4l2-ctl --all`.
- **Running a model on the MCU side.** The MCU has 786 KB SRAM. Even a tiny TFLite Micro model rarely fits. Inference belongs on the MPU.

## See also

- `bridge/SKILL.md` — required when the sketch needs to react to vision output.
- `audio/SKILL.md` — sibling skill for the other "media" capability.
- `uno-q-hardware/references/connectors.md` — JMEDIA pin layout.
- For an interactive image-capture helper, see the `camera` tool.
