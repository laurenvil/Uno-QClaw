# GStreamer pipelines on the Uno Q

GStreamer is the recommended way to use the camera and the hardware video codecs. The `v4l2*` elements in particular tap directly into the Adreno 702 GPU's hardware encoder/decoder.

## Capture a single still image

```bash
gst-launch-1.0 v4l2src device=/dev/video0 num-buffers=1 \
    ! videoconvert ! jpegenc ! filesink location=snap.jpg
```

## Live preview on a connected HDMI/DP monitor

```bash
gst-launch-1.0 v4l2src device=/dev/video0 \
    ! video/x-raw,width=1280,height=720,framerate=30/1 \
    ! videoconvert ! autovideosink
```

`autovideosink` picks the best available video sink (KMS, X11, Wayland) at runtime. Pass `kmssink` explicitly if running on a headless console.

## Record H.264 video (hardware-encoded)

```bash
gst-launch-1.0 -e v4l2src device=/dev/video0 \
    ! video/x-raw,format=NV12,width=1280,height=720,framerate=30/1 \
    ! v4l2h264enc ! h264parse ! mp4mux ! filesink location=clip.mp4
```

The `-e` flag flushes pending data on SIGINT — without it, Ctrl-C produces a corrupt MP4.

## Record H.265 (smaller files, slower encode)

```bash
gst-launch-1.0 -e v4l2src device=/dev/video0 \
    ! video/x-raw,format=NV12,width=1920,height=1080,framerate=30/1 \
    ! v4l2h265enc ! h265parse ! mp4mux ! filesink location=clip.mp4
```

## Play back an MP4 (hardware-decoded)

```bash
gst-launch-1.0 filesrc location=clip.mp4 \
    ! qtdemux name=demux demux.video_0 ! queue ! h264parse ! v4l2h264dec \
    ! videoconvert ! autovideosink
```

For H.265 source, replace `h264parse` / `v4l2h264dec` with `h265parse` / `v4l2h265dec`.

## Decode a VP9 (.webm) file

```bash
gst-launch-1.0 filesrc location=clip.webm \
    ! matroskademux ! queue ! v4l2vp9dec \
    ! videoconvert ! autovideosink
```

The Adreno 702 decodes VP9 in hardware but **does not encode** it.

## Stream camera over the network (RTSP)

```bash
# install gst-rtsp-server first: sudo apt install gstreamer1.0-rtsp
gst-launch-1.0 v4l2src device=/dev/video0 \
    ! video/x-raw,format=NV12,width=1280,height=720,framerate=30/1 \
    ! v4l2h264enc ! h264parse ! rtph264pay ! udpsink host=192.168.1.100 port=5004
```

Receiver:

```bash
gst-launch-1.0 udpsrc port=5004 caps="application/x-rtp, media=video, encoding-name=H264, payload=96" \
    ! rtph264depay ! avdec_h264 ! videoconvert ! autovideosink
```

## Concurrent encode + decode (loopback test)

```bash
gst-launch-1.0 -v videotestsrc num-buffers=1000 \
    ! video/x-raw,format=NV12,width=1280,height=720,framerate=30/1 \
    ! v4l2h264enc capture-io-mode=4 output-io-mode=2 ! h264parse \
    ! v4l2h264dec capture-io-mode=4 output-io-mode=2 ! videoconvert \
    ! autovideosink
```

Useful for stress-testing the codec pipeline before deploying a real project.

## Use from Python (`gst-python`)

```python
import gi
gi.require_version("Gst", "1.0")
from gi.repository import Gst

Gst.init(None)

pipeline = Gst.parse_launch(
    "v4l2src device=/dev/video0 ! videoconvert ! "
    "jpegenc ! appsink name=sink"
)
sink = pipeline.get_by_name("sink")
pipeline.set_state(Gst.State.PLAYING)

sample = sink.emit("pull-sample")
buf = sample.get_buffer()
ok, mapinfo = buf.map(Gst.MapFlags.READ)
with open("snap.jpg", "wb") as f:
    f.write(mapinfo.data)
buf.unmap(mapinfo)
pipeline.set_state(Gst.State.NULL)
```

## Pitfalls

- **Mixing `v4l2*` elements with software pipelines.** If you accidentally use `x264enc` (software) instead of `v4l2h264enc` (hardware), the pipeline compiles fine but CPU jumps to 95%. Always specify `v4l2h264enc`.
- **Wrong `format=`.** The Adreno expects NV12 for the hardware codecs. If your source delivers I420 or YUYV, add `videoconvert` between the source and the encoder.
- **Pipeline runs but no output.** Check the bus for errors: `gst-launch-1.0 -v ...` for verbose mode, then look for `ERROR` lines.
- **GStreamer hangs on Ctrl-C without `-e`.** Use `-e` for any recording pipeline so the muxer flushes the file index.

## See also

- `v4l2.md` for the underlying device interface.
- `opencv.md` for OpenCV integration (which uses GStreamer or V4L2 underneath).
