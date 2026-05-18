# Recording audio on the Uno Q

The Mic2 differential input on JMISC routes through the QRB2210's WCD codec and is exposed to Linux as a standard ALSA capture device.

## Find the capture device

```bash
arecord -l
```

Look for the WCD codec line, e.g.:

```
card 0: SM6225WCD9385 [SM6225-WCD9385], device 1: MultiMedia1 (*) []
```

The capture device is referenced as `hw:0,1` (card 0, device 1). To avoid hardcoding numbers, use:

```bash
arecord -L | grep -A1 capture     # list named PCM devices
```

## Record a WAV file from the command line

```bash
arecord -D hw:0,1 -f S16_LE -r 48000 -c 1 -d 5 recording.wav
```

Flags:
- `-D hw:0,1` — capture device
- `-f S16_LE` — 16-bit signed little-endian
- `-r 48000` — 48 kHz sample rate
- `-c 1` — mono
- `-d 5` — duration in seconds

For continuous recording, omit `-d`; stop with Ctrl-C.

## Verify the recording

```bash
aplay recording.wav     # play it back
file recording.wav      # confirm format: "WAVE audio, Microsoft PCM, 16 bit, mono 48000 Hz"
```

## Record from Python with `sounddevice`

```bash
pip install sounddevice numpy scipy
```

```python
import sounddevice as sd
from scipy.io.wavfile import write

duration = 5            # seconds
sample_rate = 48000

print("Recording...")
audio = sd.rec(
    int(duration * sample_rate),
    samplerate=sample_rate,
    channels=1,
    dtype="int16",
)
sd.wait()
write("recording.wav", sample_rate, audio)
print("Done.")
```

`sounddevice` uses PortAudio underneath, which uses ALSA on Linux.

## Real-time capture for voice recognition

For speech-to-text, capture in chunks and feed to a recognizer (whisper.cpp, vosk, etc.).

```python
import sounddevice as sd
import numpy as np
import queue

audio_q = queue.Queue()

def callback(indata, frames, time_info, status):
    audio_q.put(indata.copy())

with sd.InputStream(samplerate=16000, channels=1, dtype="int16", callback=callback):
    print("Listening... Ctrl-C to stop")
    while True:
        chunk = audio_q.get()
        # Hand the chunk to your STT engine here
```

For whisper.cpp, see the project's `stream` example which already implements this loop.

## Integrate with Bridge — "voice triggers a sketch action"

```python
import sounddevice as sd
import numpy as np
from arduino import Bridge

bridge = Bridge(); bridge.begin()

def on_chunk(indata, frames, time_info, status):
    # Cheap proxy for "loud noise": RMS amplitude over threshold
    rms = np.sqrt(np.mean(indata.astype(np.float32) ** 2))
    if rms > 2000:
        bridge.call("flash_led")

with sd.InputStream(samplerate=48000, channels=1, dtype="int16",
                    blocksize=4800, callback=on_chunk):
    print("Listening for loud sounds. Ctrl-C to stop.")
    sd.sleep(10_000_000)
```

MCU side exposes a `flash_led` service. See `bridge/references/mcu-side.md`.

## Adjust input gain

```bash
amixer -c 0 sset 'MIC2 Volume' 80%
```

`amixer scontrols` lists every available control. Names differ per WCD codec version.

## Pitfalls

- **No audio captured.** Mic might be muted at the mixer level. Try `amixer -c 0 sset 'MIC2 Volume' 100% unmute`.
- **Clipping / distortion.** Gain too high; lower with `amixer`.
- **Hum or 60 Hz noise.** Differential signaling requires both MIC2_INP and MIC2_INM connected to the mic; if you wire only one input single-ended you'll pick up the supply hum.
- **Recording silence.** The carrier board may have a microphone jack but no physically-connected microphone. Check that a mic capsule is actually wired.

## See also

- `audio-output.md` — playback patterns.
- `bridge/SKILL.md` — connecting audio events to the MCU sketch.
