# Real User Testing Guide

## Overview

This guide walks you through conducting systematic user testing sessions for the Virtual Trainer application. The goal is to verify that the system meets performance targets before the final demo.

**Targets:**

- Rep accuracy ≥ 90%
- Latency consistently < 100ms
- All 3 users tested before final demo

## Tools Created

1. **`user_testing.py`** - Automated testing framework that:
   - Connects to your ws_server.py
   - Tracks all metrics in real-time during the session
   - Generates detailed per-user reports
   - Saves results to JSON files

2. **`testing_summary.py`** - Aggregates results from all users:
   - Combines individual JSON reports
   - Calculates overall statistics
   - Generates the final summary table
   - Checks if you're ready for demo

## Setup Checklist

Before starting each testing session, verify:

- [ ] **ws_server.py** running on Nada's laptop

  ```bash
  cd c:\Users\MSI\Documents\GitHub\virtual-trainer
  .\venv311\Scripts\activate
  python edge/ws_server.py
  ```

- [ ] **ngrok tunnel** (if testing remotely with Douaa)

  ```bash
  ngrok http 8000
  # Share the URL (e.g., xyz123.ngrok-free.dev)
  ```

- [ ] **Ping/pong test** - Quick connection test:

  ```bash
  # On Douaa's machine:
  python logic/ws_client.py --host xyz123.ngrok-free.dev --port 443 --ssl
  # Should see connection confirmation
  ```

- [ ] **Camera setup:**
  - Position camera 2-3 meters away
  - Full body visible in frame
  - Good lighting (avoid backlighting)
  - Test with webcam preview first

- [ ] **User briefing:**
  - Explain what exercise to perform (squats)
  - Demonstrate proper form
  - Explain they'll do 2 sets of 10 reps
  - Both students should be present to observe

## Running a Test Session

### For LOCAL testing (same machine):

```bash
# 1. Start the server (Terminal 1)
python edge/ws_server.py

# 2. Run the testing session (Terminal 2)
python user_testing.py --user "User1" --height 170 --age 25 --sets 2 --reps 10

# Follow the prompts:
# - Press ENTER to start Set 1
# - Perform 10 squats
# - System will automatically detect completion
# - Press ENTER to start Set 2
# - Perform 10 squats
# - Report will be generated automatically
```

### For REMOTE testing (via ngrok):

```bash
# On testing machine (where user performs exercise):
python user_testing.py \
  --user "User2" \
  --height 165 \
  --age 23 \
  --sets 2 \
  --reps 10 \
  --host xyz123.ngrok-free.dev \
  --port 443 \
  --ssl
```

### What to observe during testing:

The script will display real-time updates:

```
Set 1 | Reps: 5 | Stage: DOWN        | Latency:  45.2ms | Landmarks: ✓
Set 1 | Reps: 6 | Stage: STANDING    | Latency:  38.7ms | Landmarks: ✓
```

Watch for:

- ✓ Landmarks detected (should always be ✓)
- Latency values (should be < 100ms)
- Rep count incrementing correctly
- Any feedback flags that appear

## After Each User

After the session completes, you'll see:

1. A detailed report printed to console
2. A JSON file saved: `user_test_User1_YYYYMMDD_HHMMSS.json`

**Save these JSON files** - you'll need them for the final summary!

## Manual Observation Notes

While the script tracks metrics automatically, manually note:

1. **Did the user perform proper form?**
   - Full depth on squats
   - Controlled movement
   - Balanced stance

2. **Any issues?**
   - User went out of frame
   - Lighting problems
   - Camera angle issues

3. **User feedback:**
   - Was the system responsive?
   - Did they notice any lag?
   - Did rep counting feel accurate?

Add these observations to the JSON file or keep separate notes.

## Testing All Users

Test 3 different users. For each user:

```bash
# User 1
python user_testing.py --user "User1" --height 170 --age 25 --sets 2 --reps 10

# User 2 (example: different height, using ngrok)
python user_testing.py --user "User2" --height 165 --age 23 --sets 2 --reps 10 \
  --host xyz123.ngrok-free.dev --port 443 --ssl

# User 3
python user_testing.py --user "User3" --height 180 --age 24 --sets 2 --reps 10
```

## Generating Final Summary

After testing all users, combine the results:

```bash
python testing_summary.py user_test_*.json
```

Or specify files explicitly:

```bash
python testing_summary.py \
  user_test_User1_20260410_143022.json \
  user_test_User2_20260410_144530.json \
  user_test_User3_20260410_150215.json
```

This will:

- Print individual user results
- Calculate overall statistics
- Show readiness checklist
- Indicate if you're ready for final demo

To save the summary:

```bash
python testing_summary.py user_test_*.json --output final_testing_summary.json
```

## Interpreting Results

### Rep Accuracy

- **≥95%**: Excellent - system is very accurate
- **90-94%**: Good - meets target
- **85-89%**: Acceptable but investigate why reps were missed
- **<85%**: Needs improvement - check thresholds or camera setup

### Latency

- **<50ms**: Excellent - very responsive
- **50-80ms**: Good - within target with margin
- **80-100ms**: Acceptable - meets target
- **>100ms**: Needs investigation - check CPU load, camera resolution

### Feedback Flags

Common flags and what they mean:

- `"knees_caving_in"` - Knee tracking during squat
- `"back_not_straight"` - Posture issue
- `"depth_insufficient"` - Squat not deep enough
- `"uneven_weight"` - Balance issue

If flags appear frequently, consider:

1. Adjusting thresholds in `THRESHOLDS` dict
2. Providing better user instruction
3. Checking if detection is too sensitive

## Troubleshooting

### "Cannot open camera"

- Check camera is not used by another application
- Try different camera index in ws_server.py (change `cap = cv2.VideoCapture(0)` to `1`)
- Verify camera permissions in Windows settings

### "No data received in 5s"

- Check ws_server.py is actually running
- Verify firewall isn't blocking connections
- For ngrok: ensure tunnel is active

### Rep count stuck at 0

- User may not be reaching full depth threshold
- Check camera can see full body
- Verify exercise is set correctly (should be "squat")

### High latency (>100ms)

- Close other CPU-intensive applications
- Check camera resolution (should be 640×480)
- Reduce FRAME_SKIP in ws_server.py if needed
- Consider testing on a more powerful machine

### Landmarks not detected

- Improve lighting in the room
- Move camera further back to see full body
- Remove obstructions or busy backgrounds
- User wearing tight/contrasting clothing helps

## Quick Command Reference

```bash
# Test locally
python user_testing.py --user "Name" --height 170 --age 25

# Test via ngrok
python user_testing.py --user "Name" --height 170 --age 25 \
  --host xyz.ngrok-free.dev --port 443 --ssl

# Different exercise
python user_testing.py --user "Name" --height 170 --age 25 --exercise lunge

# Custom sets/reps
python user_testing.py --user "Name" --height 170 --age 25 --sets 3 --reps 15

# Generate summary
python testing_summary.py user_test_*.json --output summary.json
```

## After Testing

1. Review all JSON files
2. Run testing_summary.py to get final report
3. If targets not met:
   - Analyze which users had issues
   - Check for patterns (same feedback flags?)
   - Adjust thresholds if needed
   - Consider re-testing problematic cases

4. If targets met:
   - ✓ Ready for final demo!
   - Keep JSON files as evidence
   - Document any threshold adjustments made

## Tips for Success

1. **Test in demo environment** - Use the same setup (camera, lighting, space) you'll use for the final demo
2. **Diverse users** - Test with different heights, body types for better validation
3. **Consistent instructions** - Brief all users the same way about form and procedure
4. **Take notes** - Automated metrics are great, but qualitative observations matter too
5. **Test network latency** separately if using ngrok - ping the server to measure network overhead
6. **Practice run** - Do a quick test yourself before bringing in real users

## Expected Timeline

Per user session:

- Setup & briefing: 5 minutes
- Set 1 (10 reps): 1-2 minutes
- Rest between sets: 1-2 minutes
- Set 2 (10 reps): 1-2 minutes
- Review results: 2-3 minutes

**Total per user: ~15 minutes**
**All 3 users: ~45 minutes + breaks**

Good luck with your testing! 🎯
