# Voice Coaching Layer — Coqui TTS

Real-time on-device voice coaching for the Virtual Personal Trainer.  
Runs fully offline using [Coqui TTS](https://github.com/coqui-ai/TTS) — no API key required.

---

## Installation

```bash
pip install TTS pydub
```

The TTS model (~100 MB) is downloaded automatically on first run.

---

## TTS Model

Default model: `tts_models/en/ljspeech/tacotron2-DDC`  
Fast CPU-friendly model, good English voice quality.

Override via environment variable:
```bash
export TTS_MODEL=tts_models/en/ljspeech/glow-tts
```

---

## Pre-loading Phrases

Pre-generate all ~50 coaching phrases into `voice/cache/` at startup:

```bash
python -m voice.tts_client
```

This caches every phrase as a WAV file so they play instantly during exercise.

---

## Disable Voice

```bash
export VOICE_ENABLED=0
python edge/ws_server.py
```

The server will start normally and serve pose data — just without audio.

---

## WebSocket Audio Protocol

After each pose frame with feedback, the server sends **two frames**:

**Frame 1 — JSON metadata:**
```json
{
  "type": "audio",
  "format": "wav",
  "code": "KNEE_CAVE",
  "severity": "warning",
  "text": "Drive your knees outward, don't let them collapse in.",
  "exercise": "squat"
}
```

**Frame 2 — Binary WAV:**
Raw WAV bytes (16-bit PCM, 22050 Hz). Play directly on the mobile client.

---

## Expected Latency

| Scenario | Latency |
|---|---|
| Pre-cached phrase (from disk) | < 50 ms |
| Live synthesis (new phrase, CPU) | 800–1500 ms |
| Total: flag detected → audio plays | **< 2 seconds** ✅ |

---

## File Structure

```
voice/
├── __init__.py
├── phrase_library.py     # all coaching texts (~50 phrases)
├── tts_client.py         # Coqui TTS wrapper + disk cache
├── audio_streamer.py     # WebSocket binary audio streamer
├── README.md             # this file
└── cache/                # auto-generated WAV cache (gitignored)
```