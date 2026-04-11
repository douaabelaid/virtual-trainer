# Virtual Trainer Repository - Complete Summary

**Project Name:** Virtual Trainer - AI-Powered Exercise Form Tracker  
**Last Updated:** April 11, 2026  
**Primary Language:** Python  
**Architecture:** WebSocket-based Client-Server

---

## 📋 Table of Contents
1. [Project Overview](#project-overview)
2. [Key Features](#key-features)
3. [Technology Stack](#technology-stack)
4. [Architecture](#architecture)
5. [Directory Structure](#directory-structure)
6. [File-by-File Explanation](#file-by-file-explanation)
7. [Testing Framework](#testing-framework)
8. [Usage & Deployment](#usage--deployment)

---

## 🎯 Project Overview

Virtual Trainer is a real-time AI-powered exercise form detection and coaching system that uses **MediaPipe Pose** for computer vision and **WebSocket streaming** for low-latency communication (sub-100ms). The system tracks exercises like squats, lunges, and push-ups, providing instant feedback on form, rep counting, and coaching cues.

**Core Capabilities:**
- Real-time pose detection from webcam feed
- Automatic rep counting with stage detection (STANDING → DOWN → TRANSITION)
- Form feedback based on joint angle analysis
- Remote training support via WebSocket streaming
- Comprehensive user testing framework for validation

**Target Latency:** <100ms end-to-end (webcam → pose detection → feedback)

---

## ✨ Key Features

✅ **Real-time Pose Tracking:** MediaPipe Pose with 33 landmark detection  
✅ **Exercise Detection:** Squats, Lunges, Push-ups with configurable thresholds  
✅ **Rep Counting:** Sub-100ms latency with accurate stage transitions  
✅ **Form Feedback:** Joint angle analysis with coaching messages  
✅ **WebSocket Architecture:** Scalable client-server model for remote training  
✅ **User Testing Suite:** Automated testing framework with metrics logging  
✅ **Performance Monitoring:** FPS tracking, latency measurement, frame skipping optimization  
✅ **Remote Support:** ngrok integration for remote testing/demos  

---

## 🛠️ Technology Stack

### Backend (Python)
- **FastAPI** - Async web framework for WebSocket server
- **MediaPipe** (0.10.14) - Google's pose estimation model (33 landmarks)
- **OpenCV** (4.13.0.92) - Video capture and image processing
- **Pydantic** (2.12.5) - Data validation and schema definitions
- **websockets** (16.0) - WebSocket client/server implementation
- **uvicorn** - ASGI server for FastAPI

### Frontend/Mobile (React Native)
- **react-native-vision-camera** - Camera access for mobile
- **react-native-svg** - SVG rendering for pose visualization
- **react-native-worklets-core** - High-performance JS threading
- **@react-native-community/slider** - UI components

### Testing & Development
- **pytest** (9.0.2) - Unit testing framework
- **pytest-cov** (7.1.0) - Code coverage reporting
- **matplotlib** (3.10.8) - Visualization for benchmarks
- **psutil** (7.2.2) - System resource monitoring

---

## 🏗️ Architecture

### Data Flow (Per Frame)
```
┌──────────────┐
│   Webcam     │ (640×480 BGR frames)
└──────┬───────┘
       │
       ▼
┌──────────────────────────────┐
│  PoseDetector.detect()       │ MediaPipe Pose → 33 landmarks
└──────┬───────────────────────┘
       │
       ▼
┌──────────────────────────────┐
│  _filter_landmarks()         │ Keep only 12 key joints
└──────┬───────────────────────┘
       │
       ▼
┌──────────────────────────────┐
│  ExerciseDetector.update()   │ Stage detection + Rep counting
└──────┬───────────────────────┘
       │
       ▼
┌──────────────────────────────┐
│  map_flags_to_coaching()     │ Convert flags → messages
└──────┬───────────────────────┘
       │
       ▼
┌──────────────────────────────┐
│  websocket.send_text()       │ JSON → client
└──────────────────────────────┘
```

### System Components
1. **Edge Layer** (`edge/`) - Pose detection, WebSocket server, biomechanics
2. **Logic Layer** (`logic/`) - Exercise detection, feedback mapping, angle utilities
3. **Shared Layer** (`shared/`) - Pydantic schemas for type safety
4. **Testing Layer** (`tests/`) - Unit tests for all components

### Performance Optimizations
- **Frame Skipping (FRAME_SKIP=2):** Process every 2nd frame to avoid backlog
- **Latest-Frame Queue:** maxsize=1 ensures no stale frames are processed
- **Key Landmark Filtering:** Send only 12/33 landmarks (reduces payload by ~60%)
- **JPEG Compression (quality=80):** Balance between size and quality

---

## 📂 Directory Structure

```
virtual-trainer/
│
├── edge/                           # Edge server components (pose processing)
│   ├── ws_server.py               # Main WebSocket server
│   ├── ws_server.py.bak           # Backup copy
│   ├── pose_detector.py           # MediaPipe pose detection wrapper
│   ├── biomechanics.py            # Joint angle calculations
│   ├── benchmark.py               # Performance benchmarking tool
│   └── benchmark_report.md        # Benchmark results documentation
│
├── logic/                          # Exercise detection business logic
│   ├── exercise_detector.py       # Rep counting & stage detection
│   ├── feedback_mapper.py         # Flag-to-coaching message mapping
│   ├── angle_utils.py             # Joint angle calculation utilities
│   └── ws_client.py               # WebSocket client for remote testing
│
├── shared/                         # Shared schemas and contracts
│   └── exercise_state_schema.py   # Pydantic models (ExerciseState, etc.)
│
├── tests/                          # Unit tests
│   ├── edge/                      # Tests for edge components
│   └── logic/                     # Tests for logic components
│       ├── __init__.py
│       ├── test_angle_utils.py
│       ├── test_exercise_detector.py
│       └── test_feedback_mapper.py
│
├── logs/                           # Benchmark and performance logs
│   ├── benchmark_1280x720_*.csv/json/html
│   └── benchmark_640x480_*.csv/json/html
│
├── venv311/                        # Python 3.11 virtual environment
├── new_venv/                       # Alternative virtual environment
│
├── review/                         # Code review and documentation (empty)
├── voice/                          # Voice feedback module (future)
├── virtual-trainer/                # Mobile app directory (future)
│
├── dashboard.py                    # Real-time monitoring dashboard
├── live_demo.py                    # Live demonstration script
├── send_frames.py                  # Webcam frame sender (client)
├── user_testing.py                 # Automated user testing framework
├── testing_summary.py              # Aggregate test results
├── test_connection.py              # WebSocket connection test
├── test_exercise_detector.py       # Standalone exercise detector test
├── test_live_camera.py            # Live camera feed test
├── test_ws_server.py              # WebSocket server test
├── testwsintegration.py           # WebSocket integration test
├── threshold_tuner.py             # Angle threshold tuning utility
├── session_recorder.py            # Session recording utility
├── session_user1.json             # Sample session data
│
├── README.md                       # Project documentation
├── USER_TESTING_GUIDE.md          # Guide for conducting user tests
├── TESTING_CHECKLIST.md           # QA checklist
├── requirements.txt                # Python dependencies
├── package.json                    # React Native dependencies
├── pyrightconfig.json             # Python type checker config
├── pytest.ini                      # Pytest configuration
└── pose_landmarker.task           # MediaPipe model file
```

---

## 📄 File-by-File Explanation

### **Root Directory Files**

#### `dashboard.py`
Real-time monitoring dashboard for tracking server performance, active connections, FPS, and latency metrics during live sessions.

#### `live_demo.py`
Demonstration script for showcasing the virtual trainer system in live presentations or demos.

#### `send_frames.py`
**Purpose:** WebSocket client that captures webcam frames and sends them to `ws_server.py`  
**Features:**
- Captures 640×480 frames from local camera (index 0)
- JPEG compression (quality=80) before base64 encoding
- Configurable FPS (default: 30)
- Supports remote connections via ngrok (SSL/TLS)
- Real-time overlay display showing FPS, latency, angles
- Exercise type selection via CLI args

**Usage:**
```bash
python send_frames.py --host localhost --port 8000
python send_frames.py --host ngrok.io --port 443 --ssl
```

#### `user_testing.py`
**Purpose:** Comprehensive automated testing framework for user testing sessions  
**Features:**
- Two modes: Server Camera (default) or Client Camera (`--send-frames`)
- Tracks per-set metrics: rep accuracy, latency, landmark detection rate
- Logs feedback flags and coaching messages
- Exports JSON test results for analysis
- Supports remote testing via ngrok

**Metrics Tracked:**
- Avg/max latency (ms)
- Landmark detection rate (%)
- Rep count accuracy
- Feedback flags triggered
- FPS performance

**Usage:**
```bash
python user_testing.py --user "John" --height 175 --age 25 --sets 2 --reps 10
```

#### `testing_summary.py`
Aggregates multiple user testing JSON files to generate combined statistics and reports.

#### `session_recorder.py`
Records exercise sessions to JSON format for replay, analysis, or debugging.

#### `threshold_tuner.py`
Interactive utility for calibrating angle thresholds (e.g., squat down threshold = 95°) by testing with live camera feed.

#### `test_*.py` Files
- `test_connection.py` - Validates WebSocket connection
- `test_exercise_detector.py` - Standalone unit test for ExerciseDetector
- `test_live_camera.py` - Tests live camera integration
- `test_ws_server.py` - Server functionality test
- `testwsintegration.py` - End-to-end integration test

---

### **edge/** Directory

#### `ws_server.py`
**Purpose:** Main FastAPI WebSocket server for pose processing  
**Key Components:**
- FastAPI app with CORS middleware
- WebSocket endpoint at `/ws`
- Camera thread with latest-frame queue (maxsize=1)
- Frame skipping (FRAME_SKIP=2) to prevent backlog
- Filters 33 landmarks → 12 key joints for efficiency

**Environment Variables:**
- `WS_HOST` (default: 0.0.0.0)
- `WS_PORT` (default: 8000)
- `FRAME_SKIP` (default: 2)

**Endpoints:**
- `GET /` - HTML test client
- `WS /ws` - WebSocket connection for pose data

**Data Flow:**
1. Receive base64 JPEG frame from client
2. Decode → MediaPipe Pose inference
3. Filter to 12 key landmarks
4. Calculate joint angles
5. Detect exercise stage & count reps
6. Generate feedback flags
7. Send JSON response with pose data

#### `pose_detector.py`
**Purpose:** MediaPipe Pose wrapper for landmark detection  
**Returns:** `PoseResult` dataclass containing:
- `detected` (bool) - Pose found?
- `landmarks` (list) - 33 landmarks with x, y, z, visibility
- `angles` (dict) - 8 joint angles (knees, hips, elbows, shoulders)
- `fps`, `latency_ms`, `frame_idx`

**Joint Angles Calculated:**
- left_knee, right_knee (hip-knee-ankle)
- left_hip, right_hip (shoulder-hip-knee)
- left_elbow, right_elbow (shoulder-elbow-wrist)
- left_shoulder, right_shoulder (elbow-shoulder-hip)

#### `biomechanics.py`
**Purpose:** Advanced biomechanics analysis for exercises  
**Features:**
- StateФul analyzer for single client sessions
- Phase detection (IDLE, DESCENDING, BOTTOM, ASCENDING, TOP)
- Visibility threshold validation (0.3)
- 3D angle calculations using NumPy
- Exercise-specific analysis (squat/pushup/plank)

**Classes:**
- `ExerciseType` enum (SQUAT, PUSHUP, PLANK)
- `MovementPhase` enum (IDLE, DESCENDING, BOTTOM, ASCENDING, TOP)
- `BiomechanicsAnalyzer` - Main analysis class

#### `benchmark.py`
Performance benchmarking tool that measures FPS, latency, and CPU usage under various resolutions and conditions.

#### `benchmark_report.md`
Documentation of benchmark results showing system performance metrics.

---

### **logic/** Directory

#### `exercise_detector.py`
**Purpose:** Core exercise detection and rep counting logic  
**Classes:**
- `ExerciseDetector` - Main detector class

**Methods:**
- `__init__(exercise="squat")` - Initialize with exercise type
- `reset()` - Reset rep count and stage
- `detect_stage(angles)` - Determine current stage (STANDING/DOWN/TRANSITION)
- `update(landmarks)` - Process landmarks → ExerciseState
- `check_feedback(angles)` - Generate feedback flags

**Angle Thresholds:**
```python
THRESHOLDS = {
    "squat": {
        "down": {"left_knee": 95, "right_knee": 95},
        "standing": {"left_knee": 160, "right_knee": 160}
    },
    "pushup": {
        "down": {"left_elbow": 90, "right_elbow": 90},
        "standing": {"left_elbow": 160, "right_elbow": 160}
    },
    "lunge": {
        "down": {"left_knee": 90, "right_knee": 90},
        "standing": {"left_knee": 160, "right_knee": 160}
    }
}
```

**Rep Counting Logic:**
- Sets `_was_down = True` when stage == DOWN
- Increments rep when `_was_down && stage == STANDING`
- Supports transitional states (DOWN → TRANSITION → STANDING)

#### `feedback_mapper.py`
**Purpose:** Maps feedback flag codes to human-readable coaching messages  
**Categories:**
- **Squat:** KNEE_CAVE, TOO_SHALLOW, DEPTH_OK, BACK_ANGLE
- **Push-up:** PUSHUP_TOO_SHALLOW, ELBOW_FLARE
- **Lunge:** KNEE_TOO_FORWARD
- **General:** GOOD_FORM

**Example Mapping:**
```python
"KNEE_CAVE": [
    "Drive your knees outward, don't let them collapse in.",
    "Push your knees out in line with your toes.",
    "Your knees are caving — spread them wide."
]
```

**Function:**
- `map_flags_to_coaching(flags)` - Converts flag list → message list

#### `angle_utils.py`
**Purpose:** Utility functions for joint angle calculations  
**Key Function:**
- `get_joint_angles(landmarks)` - Calculates all 8 joint angles from landmark dict
- Uses 3-point angle formula: arccos of dot product between vectors
- Returns dict with keys: left_knee, right_knee, left_hip, right_hip, left_elbow, right_elbow, left_shoulder, right_shoulder

#### `ws_client.py`
WebSocket client implementation for remote testing and connecting to the server from external applications.

---

### **shared/** Directory

#### `exercise_state_schema.py`
**Purpose:** Pydantic data models for type safety and API contracts  
**Status:** Schema locked as of March 2026 (no changes without approval)

**Models:**

1. **ExerciseType** (Enum)
   - SQUAT, PUSHUP, LUNGE

2. **ExerciseStage** (Enum)
   - STANDING, DOWN, TRANSITION

3. **FeedbackSeverity** (Enum)
   - INFO, WARNING, ERROR

4. **FeedbackFlag** (Model)
   ```python
   code: str
   message: str
   severity: FeedbackSeverity
   ```

5. **JointAngles** (Model)
   ```python
   left_knee, right_knee: Optional[float]
   left_hip, right_hip: Optional[float]
   back: Optional[float]
   left_elbow, right_elbow: Optional[float]
   ```

6. **LandmarkPoint** (Model)
   ```python
   x: float
   y: float
   ```

7. **ExerciseState** (Model) - Main contract
   ```python
   timestamp_ms: int
   exercise: ExerciseType
   stage: ExerciseStage
   rep_count: int
   joint_angles: JointAngles
   ```

---

### **tests/** Directory

#### `tests/logic/test_angle_utils.py`
Unit tests for angle calculation functions. Tests edge cases like zero-length vectors, 180° angles, and landmark visibility.

#### `tests/logic/test_exercise_detector.py`
Comprehensive tests for ExerciseDetector:
- Stage detection accuracy
- Rep counting logic
- Threshold validation
- Feedback flag generation
- Reset functionality

#### `tests/logic/test_feedback_mapper.py`
Tests for feedback message mapping:
- Flag-to-message conversion
- Multiple flag handling
- Unknown flag handling

---

### **Configuration Files**

#### `requirements.txt`
Python dependencies with locked versions (48 packages total). Key packages:
- mediapipe==0.10.14
- opencv-contrib-python==4.13.0.92
- fastapi==0.135.1
- websockets==16.0
- pydantic==2.12.5
- pytest==9.0.2

#### `package.json`
React Native dependencies for mobile app:
- @react-native-community/slider
- react-native-svg
- react-native-vision-camera
- react-native-worklets-core

#### `pytest.ini`
Pytest configuration for test discovery and execution.

#### `pyrightconfig.json`
Pyright (static type checker) configuration for Python type checking.

#### `pose_landmarker.task`
MediaPipe pre-trained model file for pose landmark detection (binary file).

---

### **Documentation Files**

#### `README.md`
Main project documentation covering:
- Quick start guide
- Installation instructions
- User testing framework
- Remote testing via ngrok
- Project structure overview

#### `USER_TESTING_GUIDE.md`
Detailed guide for conducting systematic user testing sessions before demos.

#### `TESTING_CHECKLIST.md`
QA checklist for validating system functionality before releases.

#### `session_user1.json`
Sample JSON output from a user testing session (reference format).

---

## 🧪 Testing Framework

### Unit Tests
Located in `tests/logic/` and `tests/edge/`:
- **Test Coverage:** Angle calculations, exercise detection, feedback mapping
- **Framework:** pytest with pytest-cov for coverage reports
- **Run Command:** `pytest` or `pytest tests/logic/test_exercise_detector.py`

### Integration Tests
- `testwsintegration.py` - End-to-end WebSocket flow
- `test_connection.py` - Server connectivity validation

### User Testing Framework
**File:** `user_testing.py`  
**Purpose:** Systematic user testing with metrics logging  
**Outputs:** JSON files with per-set metrics

**Metrics Logged:**
- Rep count accuracy
- Average/max latency (ms)
- Landmark detection rate (%)
- Feedback flags triggered
- FPS performance
- Set duration

**Workflow:**
1. Run server: `python edge/ws_server.py`
2. Execute test: `python user_testing.py --user "Name" --height 170 --age 25 --sets 2 --reps 10`
3. Perform exercises in front of camera
4. Press 's' to start each set, 'e' to end
5. Review generated `user_test_*.json` file
6. Aggregate results: `python testing_summary.py user_test_*.json`

### Performance Benchmarking
**File:** `edge/benchmark.py`  
**Outputs:** CSV, JSON, HTML reports in `logs/`  
**Measures:** FPS, latency, CPU usage at different resolutions

---

## 🚀 Usage & Deployment

### Local Development

1. **Activate Virtual Environment:**
   ```powershell
   .\venv311\Scripts\Activate.ps1
   ```

2. **Install Dependencies:**
   ```bash
   pip install -r requirements.txt
   ```

3. **Start Server:**
   ```bash
   python edge/ws_server.py
   ```
   Server runs at `ws://0.0.0.0:8000/ws`

4. **Test with Local Camera:**
   ```bash
   python send_frames.py
   ```

### Remote Testing (via ngrok)

1. **Start ngrok tunnel:**
   ```bash
   ngrok http 8000
   ```

2. **Share ngrok URL with remote tester**

3. **Remote tester connects:**
   ```bash
   python user_testing.py --user "Name" --height 170 --age 25 \
     --host xyz123.ngrok-free.dev --port 443 --ssl
   ```

### Production Deployment Considerations

- **Scaling:** Use process managers (PM2, systemd) for multi-instance deployment
- **Security:** Implement authentication for WebSocket connections
- **Monitoring:** Integrate logging with centralized systems (ELK, Splunk)
- **Frame Optimization:** Adjust FRAME_SKIP based on server CPU capacity
- **Mobile App:** React Native app in `virtual-trainer/` directory (in development)

---

## 📊 Performance Metrics

### Benchmarks (640×480 resolution)
- **FPS:** ~15-30 FPS (depending on CPU)
- **Latency:** 50-100ms end-to-end
- **CPU Usage:** ~30-40% on modern processors
- **Landmark Detection:** 95%+ accuracy in good lighting

### Optimizations Applied
1. **Frame Skipping (FRAME_SKIP=2):** Prevents processing backlog
2. **Landmark Filtering:** Send 12/33 landmarks (~60% size reduction)
3. **JPEG Compression (quality=80):** Balances quality vs. bandwidth
4. **Latest-Frame Queue:** Ensures no stale frames are processed
5. **Async WebSocket:** Non-blocking I/O for multiple clients

---

## 🔮 Future Enhancements

### Planned Features
- **Voice Feedback** (`voice/` directory) - TTS coaching cues
- **Mobile App** (`virtual-trainer/` directory) - React Native client
- **Additional Exercises** - Deadlifts, planks, burpees
- **Multi-User Sessions** - Group training support
- **Cloud Deployment** - AWS/Azure hosting with auto-scaling
- **Advanced Analytics** - ML-based form prediction and correction

### Research Areas
- Improve landmark detection in poor lighting
- Reduce latency to <50ms with edge computing
- Add depth sensing for 3D pose analysis
- Integrate with wearable sensors (heart rate, acceleration)

---

## 💡 Key Design Decisions

1. **WebSocket vs HTTP:** Chosen for low-latency bidirectional streaming
2. **MediaPipe vs Custom Model:** MediaPipe offers production-ready accuracy with minimal setup
3. **12 vs 33 Landmarks:** Filtered to essential joints for bandwidth efficiency
4. **Client-Side Camera vs Server-Side:** Supports both for flexibility (default: server-side)
5. **Frame Skipping:** Essential to prevent inference backlog on CPU-only systems
6. **Latest-Frame Queue:** Prioritizes real-time feedback over processing every frame
7. **Pydantic Schemas:** Type safety and clear API contracts between layers

---

## 📞 Contact & Contributions

**Project Status:** Active Development  
**Last Major Update:** March 2026 (Schema lock)  
**Contributors:** Development team  
**License:** Not specified in repository  

For questions, issues, or contributions, refer to the project's version control system and team communication channels.

---

**End of Repository Summary**  
*Generated on April 11, 2026*
