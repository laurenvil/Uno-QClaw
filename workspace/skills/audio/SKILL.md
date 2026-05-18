---
name: audio
description: Audio capture and playback on the Uno Q — the QRB2210 exposes analog Mic2 (INP/INM/BIAS), Headphone L/R + REF, LineOut P/M, Earpiece P/R, and HS_DET (headset detect) through the JMISC header. All audio runs through Linux ALSA on the MPU side. Read this BEFORE writing any project that records audio, plays sound, does voice recognition, or makes the board talk.
---

# Audio on the Uno Q

The Uno Q exposes analog audio endpoints on the **JMISC** header (designator B1). They are:

| Endpoint | Purpose | Type |
|---|---|---|
| **Mic2 INP / INM / BIAS** | Differential microphone input with bias | Input (analog) |
| **HPH_L / HPH_R / HPH_REF** | Stereo headphone output | Output (analog) |
| **LINEOUT_P / LINEOUT_M** | Differential line-level output | Output (analog) |
| **EAR_P_R / EAR_M_R** | Earpiece (mono) output | Output (analog) |
| **HS_DET** | Headset detect (TRRS plug-in detection) | Input (control) |

All audio is **MPU-owned** — wired into the QRB2210's WCD codec, exposed to Linux as standard **ALSA** devices. The MCU has no direct audio path. Sketches that need to play or capture audio call Python via Bridge.

## When to use

| Lesson scenario | Approach |
|---|---|
| Play a WAV file when a button is pressed | MCU notifies on press → Python plays via `aplay` or `simpleaudio` |
| Record from a connected microphone | `arecord` on the command line, or `sounddevice` in Python |
| Voice-controlled LED — say "on", LED lights up | Python runs whisper.cpp / vosk on captured audio → Bridge call to MCU |
| Beep / tone generator | MCU's DAC0/DAC1 (A0/A1) for pure analog tones, or play a WAV from Linux for richer audio |
| Text-to-speech | Python `pyttsx3` or `espeak` → ALSA |
| Audio reactive light show | Python captures audio → FFT → Bridge calls MCU to set LED colors |

## Quick rules

1. **Audio runs on Linux.** Use ALSA tools (`aplay`, `arecord`, `amixer`) or Python wrappers (`sounddevice`, `pyaudio`, `simpleaudio`).
2. **JMISC requires a carrier board** to break out the analog audio pins to jacks, speakers, or microphone amplifiers. You can't probe the 60-pin JMISC directly for audio.
3. **Mic2 needs bias.** The `MIC2_BIAS` pin provides DC bias for an electret-style mic capsule. Use it; don't try to AC-couple a mic without bias.
4. **Headphone output drives ~16–32 Ω headphones directly.** For a speaker, route through a small amplifier (PAM8403 or similar) — the headphone amp can't drive a 4 Ω speaker safely.
5. **Sample rates** are configured per device; 48 kHz is typical and well-supported. 44.1 kHz works too.
6. **For voice recognition**, do the capture and the inference on Linux (whisper.cpp, vosk, etc.); send the recognized text to the MCU as a Bridge call if needed.

## Reference files

- `references/mic-record.md` — capture audio with `arecord` and Python `sounddevice`.
- `references/audio-output.md` — play WAV/MP3 files, generate tones, text-to-speech.

## Pitfalls

- **Trying to use the MCU's DAC for "audio".** DAC0/DAC1 (A0/A1) can generate analog waveforms up to a few kHz, fine for tones but not music. For real audio use the MPU's analog endpoints on JMISC.
- **Plugging a microphone straight into Mic2 without bias.** Most electret mics need DC bias — connect MIC2_BIAS through a resistor to the mic's hot pin (consult the mic capsule datasheet for the exact value, usually 1–10 kΩ).
- **Plugging a 4 Ω speaker into HPH_L/R.** Will distort and may damage the codec. Use 16+ Ω headphones, or an external amplifier.
- **ALSA device numbering shifts.** USB audio devices appear as `card1`, `card2`... depending on enumeration order. Use names (e.g., `hw:CARD=USB,DEV=0`) or `default` rather than numeric indices in production scripts.
- **Skipping `HS_DET`.** This pin tells Linux whether a headset (TRRS) is plugged in vs a headphone (TRS). Routing logic uses it to switch between speaker and headphone output. Carrier boards usually wire HS_DET to a jack with a detect switch.

## See also

- `bridge/SKILL.md` — connecting audio events to the MCU sketch.
- `uno-q-hardware/references/connectors.md` — the JMISC pin layout.
- `wireless/SKILL.md` — for streaming audio over Bluetooth A2DP (uses the same ALSA path).
