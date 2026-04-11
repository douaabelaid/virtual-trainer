# Audio Streaming Quick Start

## 🚀 Quick Start (5 minutes)

### 1. Start Server with Audio Enabled

```bash
cd /workspaces/virtual-trainer
source .venv/bin/activate

# Default: Audio forwarding enabled
export AUDIO_ENABLED=1
export AUDIO_MODE=forward

python edge/ws_server.py
```

### 2. Test Audio Module

```bash
# In another terminal
python test_audio_integration.py module
```

Expected output:
```
✅ AudioStreamer initialized
✅ Clients registered
✅ Audio message created
✅ Cooldown working correctly
✅ All audio module tests passed!
```

### 3. Send Test Audio (with server running)

```bash
python test_audio_integration.py server
```

## 📋 Protocol Reference

### Backend → Edge: Send Audio Feedback

```json
{
  "type": "audio_feedback",
  "audio_data": "<base64-encoded WAV>",
  "code": "KNEE_CAVE",
  "severity": "warning",
  "text": "Keep knees aligned",
  "format": "wav"
}
```

### Edge → Mobile: Audio Metadata + Binary Data

**Frame 1 (JSON):**
```json
{
  "type": "audio_metadata",
  "format": "wav",
  "code": "KNEE_CAVE",
  "severity": "warning",
  "text": "Keep knees aligned",
  "duration_ms": 1200,
  "sample_rate": 16000,
  "channels": 1
}
```

**Frame 2 (Binary):**
```
<binary WAV audio data>
```

## 🔧 Configuration

### Environment Variables

```bash
# Enable/disable audio
export AUDIO_ENABLED=1              # 1=on, 0=off

# Streaming mode
export AUDIO_MODE=forward           # forward/local/both

# Optional: Quality settings
export AUDIO_SAMPLE_RATE=16000      # Hz
export AUDIO_COOLDOWN_MS=500        # Min time between clips
```

### Mode Options

| Mode | Description | Use Case |
|------|-------------|----------|
| `forward` | Send to mobile client | Production (default) |
| `local` | Play on server | Testing/debugging |
| `both` | Forward + play locally | Development |

## 📱 Mobile Client Example

```javascript
const ws = new WebSocket("wss://your-edge-server:8765");
let expectingAudio = false;

ws.binaryType = "blob";  // Important!

ws.onmessage = (event) => {
  // Binary frame = audio data
  if (event.data instanceof Blob && expectingAudio) {
    const audio = new Audio(URL.createObjectURL(event.data));
    audio.play();
    expectingAudio = false;
    return;
  }
  
  // Text frame = JSON
  const msg = JSON.parse(event.data);
  
  switch(msg.type) {
    case "pose":
      // Handle video pipeline (unchanged)
      updatePose(msg.landmarks);
      break;
      
    case "audio_metadata":
      // Audio incoming, expect binary next
      console.log(`Audio: ${msg.code} - ${msg.text}`);
      expectingAudio = true;
      break;
  }
};
```

## 🔍 Debugging

### Check Audio Status

```bash
# Server logs on startup
🚀 Virtual Trainer — Pose Detection Edge Server (Phase 2)
   ...
   Audio enabled   : YES (mode: forward)  ← Should see this
```

### Test Audio Pipeline

```bash
# Test 1: Module only
python test_audio_integration.py module

# Test 2: Full integration (requires running server)
python edge/ws_server.py &            # Start server
sleep 2
python test_audio_integration.py server  # Test streaming
```

### Common Issues

**"Audio not enabled"**
```bash
export AUDIO_ENABLED=1
python edge/ws_server.py
```

**"Audio dropped (cooldown)"**  
Wait 500ms between audio clips or adjust:
```bash
export AUDIO_COOLDOWN_MS=200  # Reduce to 200ms
```

**"Audio arrives delayed"**  
Reduce file size or sample rate:
```bash
export AUDIO_SAMPLE_RATE=8000  # Lower quality but faster
```

## 📊 Performance

| Metric | Value |
|--------|-------|
| Overhead on video pipeline | < 0.1ms |
| Memory per client | ~20 KB |
| Audio clip size (1s speech) | 2-5 KB |
| Cooldown (default) | 500ms |

## 📚 Full Documentation

See [AUDIO_STREAMING.md](AUDIO_STREAMING.md) for complete documentation.

## ✅ Checklist

- [ ] Server starts with "Audio enabled: YES"
- [ ] Module test passes (all 7 tests)
- [ ] Integration test connects and sends audio
- [ ] Mobile client receives binary frames
- [ ] Audio plays on mobile device

---

**Need help?** Check [AUDIO_STREAMING.md](AUDIO_STREAMING.md) for troubleshooting
