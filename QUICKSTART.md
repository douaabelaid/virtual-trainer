# Virtual Trainer - Quick Start Guide

## ✅ FIXES APPLIED

**Problem:** Port mismatch between components  
**Solution:** Changed `ws_server.py` default port from 8765 → **8000**

All components now use **port 8000** by default.

---

## 🚀 How to Run User Testing

### Step 1: Start the Server (Student A - Nada's laptop with webcam)

```bash
cd c:\Users\MSI\Documents\GitHub\virtual-trainer
.\venv311\Scripts\Activate.ps1
python edge/ws_server.py
```

**What this does:**

- ✅ Opens webcam directly (cv2.VideoCapture)
- ✅ Runs MediaPipe Pose detection
- ✅ Runs exercise detector (squat/lunge/pushup)
- ✅ Serves WebSocket on `ws://0.0.0.0:8000/ws`
- ✅ Sends real-time pose data to connected clients

**You should see:**

```
[INFO] Camera ready (640x480).
[INFO] Server ready - ws://0.0.0.0:8000/ws
```

---

### Step 2: Run User Testing (can be on same or different laptop)

**Option A: Test on the same machine**

```bash
# In a NEW terminal window
cd c:\Users\MSI\Documents\GitHub\virtual-trainer
.\venv311\Scripts\Activate.ps1
python user_testing.py --user "Nada" --height 165 --age 22 --sets 2 --reps 10
```

**Option B: Test from a different laptop on the same network**

```bash
# First, find the server's IP address (on server machine):
ipconfig  # Look for IPv4 Address (e.g., 192.168.1.100)

# Then on your laptop:
python user_testing.py --user "Douaa" --height 170 --age 23 --sets 2 --reps 10 --host 192.168.1.100 --port 8000
```

**What this does:**

- ✅ Connects to `ws://127.0.0.1:8000/ws` (or specified host)
- ✅ Receives live pose data from the server
- ✅ Logs rep counts, latency, accuracy
- ✅ Saves results to JSON file

---

### Step 3: Perform the Exercise

1. Stand in front of the **server's webcam** (Student A's laptop)
2. Press ENTER when ready
3. Do 10 squats for Set 1
4. Press ENTER for Set 2
5. Do 10 more squats
6. Results automatically saved!

---

## 📊 Output Files

After testing, you'll get a JSON file like:

```
user_test_Nada_20260411_153045.json
```

Contains:

- Rep accuracy (target: ≥90%)
- Mean latency (target: <100ms)
- Landmark detection rate
- Feedback flags triggered
- Per-set breakdown

---

## ⚠️ Important Notes

### ✅ What You DON'T Need:

- ❌ **send_frames.py** - ws_server.py already captures from webcam!
- ❌ ngrok (unless testing remotely)
- ❌ Multiple cameras

### ✅ What You DO Need:

- ✅ Server machine must have a working webcam
- ✅ Person doing squats must be in front of the **server's camera**
- ✅ Both machines on same network (if testing remotely)
- ✅ Port 8000 accessible

---

## 🔧 Troubleshooting

### "No data received in 5s"

- ✅ Check server is running: `python edge/ws_server.py`
- ✅ Check server shows "Camera ready (640x480)"
- ✅ Check port 8000 is correct
- ✅ Person must be visible in webcam frame

### "Cannot open camera"

- ✅ Close other apps using webcam (Zoom, Teams, etc.)
- ✅ Try `cap = cv2.VideoCapture(0)` or `VideoCapture(1)`
- ✅ Check webcam permissions

### "Connection refused"

- ✅ Server must be running first
- ✅ Check firewall allows port 8000
- ✅ Use correct IP address for remote testing

---

## 📁 File Responsibilities

**Student A (Nada):**

- ✅ [edge/ws_server.py](edge/ws_server.py) - **Changed PORT from 8765 to 8000**
- ✅ [edge/pose_detector.py](edge/pose_detector.py) - No changes needed
- ✅ [edge/biomechanics.py](edge/biomechanics.py) - No changes needed
- ✅ [edge/benchmark.py](edge/benchmark.py) - No changes needed
- ✅ [send_frames.py](send_frames.py) - No longer needed!

**Student B (Douaa):**

- ✅ [logic/exercise_detector.py](logic/exercise_detector.py) - No changes needed
- ✅ [logic/feedback_mapper.py](logic/feedback_mapper.py) - No changes needed
- ✅ [logic/angle_utils.py](logic/angle_utils.py) - No changes needed
- ✅ [logic/ws_client.py](logic/ws_client.py) - No changes needed

**Shared:**

- ✅ [user_testing.py](user_testing.py) - Already uses port 8000, no changes needed!

---

## 🎯 Expected Results

**Good results:**

- Rep accuracy: ≥90% (e.g., 9-10 reps detected out of 10 actual)
- Mean latency: <100ms
- Landmark detection: >95%

**If accuracy is low:**

- ✅ Ensure full body visible in frame
- ✅ Good lighting
- ✅ Perform squats slowly and deliberately
- ✅ Go to full depth (knees ~90°)

---

## 🔄 Data Flow

```
┌──────────────────────────────────────────────────────────────┐
│  ws_server.py (Student A's laptop - port 8000)               │
│                                                              │
│  Camera Thread         WebSocket Handler                    │
│  ┌──────────┐          ┌──────────────┐                     │
│  │ Webcam   │──frame──>│ MediaPipe    │                     │
│  │ 640×480  │          │ Pose         │                     │
│  └──────────┘          │              │                     │
│                        │ Exercise     │                     │
│                        │ Detector     │──JSON──> Client     │
│                        │              │                     │
│                        │ Feedback     │                     │
│                        │ Mapper       │                     │
│                        └──────────────┘                     │
└──────────────────────────────────────────────────────────────┘
                              │
                              │ ws://host:8000/ws
                              │
                              ▼
                    ┌──────────────────┐
                    │ user_testing.py  │
                    │                  │
                    │ - Receives data  │
                    │ - Logs metrics   │
                    │ - Saves JSON     │
                    └──────────────────┘
```

---

## ✅ Testing Checklist

- [ ] Server starts without errors
- [ ] Server logs show "Camera ready (640x480)"
- [ ] Server logs show "Server ready - ws://0.0.0.0:8000/ws"
- [ ] user_testing.py connects successfully
- [ ] Real person visible in webcam frame
- [ ] Reps are counted correctly
- [ ] JSON file is generated with results
- [ ] Rep accuracy ≥90%
- [ ] Mean latency <100ms

---

## Summary of Changes

**File:** [edge/ws_server.py](edge/ws_server.py)  
**Line 52:** `PORT = int(os.getenv('WS_PORT', '8000'))` (was 8765)  
**Line 298:** Updated HTML response to show correct port

**No other files needed changes!** The webcam capture was already implemented.
