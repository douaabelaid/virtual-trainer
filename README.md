# Virtual Trainer - AI-Powered Exercise Form Tracker

Real-time exercise form detection and coaching using MediaPipe Pose and WebSocket streaming.

## Features

- ✅ Real-time pose detection via webcam
- ✅ Exercise tracking: Squats, Lunges, Push-ups
- ✅ Rep counting with sub-100ms latency
- ✅ Form feedback and coaching cues
- ✅ WebSocket-based architecture for remote training
- ✅ Comprehensive user testing framework

## Quick Start

### 1. Install Dependencies

```bash
# Activate virtual environment
.\venv311\Scripts\activate

# Install requirements
pip install -r requirements.txt
```

### 2. Run the Server

```bash
python edge/ws_server.py
```

Server will start on `ws://0.0.0.0:8000/ws`

### 3. Test Locally

```bash
# Stream from local webcam
python send_frames.py
```

## User Testing

For systematic user testing before demos, use the automated testing framework:

```bash
# Run a test session
python user_testing.py --user "John" --height 175 --age 25 --sets 2 --reps 10

# Combine results from multiple users
python testing_summary.py user_test_*.json
```

See [USER_TESTING_GUIDE.md](USER_TESTING_GUIDE.md) for detailed instructions.

## Remote Testing (via ngrok)

```bash
# 1. Start ngrok tunnel
ngrok http 8000

# 2. Share ngrok URL with remote tester

# 3. Remote tester runs:
python user_testing.py --user "Name" --height 170 --age 25 \
  --host xyz123.ngrok-free.dev --port 443 --ssl
```

## Project Structure

```
├── edge/                    # Edge server components
│   ├── ws_server.py        # Main WebSocket server
│   ├── pose_detector.py    # MediaPipe pose detection
│   └── biomechanics.py     # Angle calculations
│
├── logic/                   # Exercise detection logic
│   ├── exercise_detector.py  # Rep counting & stage detection
│   ├── feedback_mapper.py    # Form feedback generation
│   ├── angle_utils.py        # Joint angle utilities
│   └── ws_client.py          # Client for remote testing
│
├── shared/                  # Shared schemas
│   └── exercise_state_schema.py
│
├── tests/                   # Unit tests
│
├── user_testing.py         # Automated user testing framework
├── testing_summary.py      # Aggregate test results
└── send_frames.py          # Webcam frame sender
```

## Testing

```bash
# Run unit tests
pytest

# Run specific test file
pytest tests/logic/test_exercise_detector.py

# With coverage
pytest --cov=logic
```

## Performance Targets

- **Rep Accuracy**: ≥90%
- **Latency**: <100ms (processing time)
- **Frame Rate**: 30 FPS
- **Landmark Detection**: >95% of frames

## Exercise Configuration

Thresholds can be adjusted in `logic/exercise_detector.py`:

```python
THRESHOLDS = {
    "squat": {
        "down":     {"left_knee": 95,  "right_knee": 95},
        "standing": {"left_knee": 160, "right_knee": 160},
    },
    # ... more exercises
}
```

## Camera Setup

For best results:

- Position camera 2-3 meters away
- Ensure full body is visible
- Good lighting (avoid backlighting)
- Clean background
- Camera at waist height

## Troubleshooting

### High Latency

- Close other CPU-intensive apps
- Check camera resolution (640×480 recommended)
- Reduce `FRAME_SKIP` in ws_server.py

### Rep Count Inaccurate

- Verify full range of motion
- Check camera angle (full body visible)
- Adjust thresholds if needed

### Connection Issues

- Verify ws_server.py is running
- Check firewall settings
- For ngrok: ensure tunnel is active

## License

[Your License Here]

## Contributors

- Nada (Server/Backend)
- Douaa (Client/Testing)
