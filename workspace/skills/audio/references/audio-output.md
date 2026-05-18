# Playing audio on the Uno Q

The Headphone L/R, LineOut P/M, and Earpiece P/R outputs on JMISC route through the QRB2210's WCD codec and are exposed to Linux as standard ALSA playback devices.

## Find the playback device

```bash
aplay -l
```

Typical:

```
card 0: SM6225WCD9385 [SM6225-WCD9385], device 0: MultiMedia0 (*) []
```

Playback device: `hw:0,0`.

## Play a WAV file from the command line

```bash
aplay -D hw:0,0 sound.wav
```

For MP3 / OGG / FLAC:

```bash
sudo apt install mpg123 ogg123 flac
mpg123 song.mp3
ogg123 song.ogg
```

## Play from Python with `simpleaudio`

```bash
pip install simpleaudio
```

```python
import simpleaudio as sa

wave_obj = sa.WaveObject.from_wave_file("sound.wav")
play_obj = wave_obj.play()
play_obj.wait_done()
```

## Generate a tone

```python
import numpy as np
import simpleaudio as sa

freq = 440           # Hz (A4)
duration = 1         # seconds
sample_rate = 48000

t = np.linspace(0, duration, int(sample_rate * duration), endpoint=False)
tone = (0.3 * np.sin(2 * np.pi * freq * t) * 32767).astype(np.int16)

play_obj = sa.play_buffer(tone, 1, 2, sample_rate)
play_obj.wait_done()
```

## Text-to-speech with `espeak`

```bash
sudo apt install espeak-ng
espeak-ng "Hello from the Uno Q"
```

From Python:

```bash
pip install pyttsx3
```

```python
import pyttsx3
engine = pyttsx3.init()
engine.say("Hello from the Uno Q")
engine.runAndWait()
```

## Integrate with Bridge — "button press triggers a sound"

```python
import simpleaudio as sa
from arduino import Bridge

bridge = Bridge(); bridge.begin()
sound = sa.WaveObject.from_wave_file("ding.wav")

def on_press(pin):
    sound.play()  # don't wait — return immediately so Bridge stays responsive

bridge.subscribe("button_pressed", on_press)
bridge.run_forever()
```

MCU sketch pushes `button_pressed` notifications (see `bridge/references/mcu-side.md`).

## Route between headphone and speaker

The WCD codec auto-routes based on the `HS_DET` pin: plug detected → headphone, no plug → built-in speaker (or LineOut). To force a route, use the ALSA mixer:

```bash
amixer -c 0 sset 'HPHL Volume' 90%
amixer -c 0 sset 'HPHR Volume' 90%
amixer -c 0 sset 'EAR Volume' 0%      # mute earpiece
```

Control names depend on the carrier board's mapping; `amixer scontrols` lists what's available.

## Volume control

```bash
amixer -c 0 sset 'HPH_Boost Volume' 50%
```

For Python control without shelling out:

```python
import alsaaudio
mixer = alsaaudio.Mixer(control="HPH_Boost", cardindex=0)
mixer.setvolume(50)
```

## Pitfalls

- **No sound from `aplay`.** Check `amixer` — the channel might be muted (`[off]` instead of `[on]`).
- **Crackling at high volumes.** Driver clipping or speaker overdrive. Lower the digital volume and/or the analog amp gain.
- **MP3 / WAV plays but distorted.** Sample rate mismatch — `aplay` resamples on the fly, but the resampler is crude. Convert the file to 48 kHz with `sox` first: `sox in.wav -r 48000 out.wav`.
- **Latency for tone generation.** PortAudio default buffer is ~50–200 ms. For low-latency audio (musical instruments), set `blocksize` explicitly and reduce.
- **Headphone amp can't drive a 4 Ω speaker.** Route through an external amp (PAM8403, MAX98357A, etc.) — they take I²S or analog and drive 4–8 Ω speakers cleanly.

## See also

- `mic-record.md` — capture patterns.
- `bridge/SKILL.md` — connecting playback to sketch events.
