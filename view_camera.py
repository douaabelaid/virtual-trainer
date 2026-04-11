"""
view_camera.py - Simple camera viewer with pose detection
Shows live camera feed with landmarks and rep counting.

Usage:
    python view_camera.py
"""

import cv2
import time
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from edge.pose_detector import PoseDetector
from logic.exercise_detector import ExerciseDetector

def main():
    print("=== Virtual Trainer - Camera Viewer ===")
    print("Opening camera...")
    
    # Open camera
    cap = cv2.VideoCapture(0)
    if not cap.isOpened():
        print("❌ Cannot open camera!")
        return
    
    cap.set(cv2.CAP_PROP_FRAME_WIDTH, 640)
    cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 480)
    print("✅ Camera opened (640x480)")
    
    # Initialize pose detector (with lower thresholds for better stability)
    print("Initializing MediaPipe...")
    pose_detector = PoseDetector(
        model_complexity=1,           # Better quality
        min_detection_conf=0.3,       # Lower = easier to detect (was 0.5)
        min_tracking_conf=0.3,        # Lower = better tracking (was 0.5)
        target_fps=30,
        min_visibility=0.2            # Lower = accept more landmarks (was 0.3)
    )
    pose_detector.warmup()
    print("✅ MediaPipe ready")
    
    # Initialize exercise detector
    print("Initializing exercise detector...")
    exercise_detector = ExerciseDetector(exercise='squat')
    print("✅ Exercise detector ready")
    
    print("\n🎥 Camera window will open - Press 'q' to quit\n")
    
    # Create window (smaller size)
    cv2.namedWindow('Virtual Trainer', cv2.WINDOW_NORMAL)
    cv2.resizeWindow('Virtual Trainer', 800, 600)
    
    frame_count = 0
    start_time = time.time()
    
    while True:
        ret, frame = cap.read()
        if not ret:
            print("⚠️ Failed to read frame")
            continue
        
        frame_count += 1
        
        # Create display frame
        display = frame.copy()
        h, w = display.shape[:2]
        
        # Detect pose
        result = pose_detector.detect_bgr(frame)
        
        if result.detected and result.landmarks:
            # Draw all landmarks (green)
            for lm in result.landmarks:
                if lm.get('visible', False):
                    x = int(lm['x'] * w)
                    y = int(lm['y'] * h)
                    # Draw circle (green for detected)
                    cv2.circle(display, (x, y), 6, (0, 255, 0), -1)
                    cv2.circle(display, (x, y), 8, (255, 255, 255), 1)
            
            # Get key landmarks for exercise detection
            key_landmarks = {}
            for name in ['left_hip', 'right_hip', 'left_knee', 'right_knee', 
                        'left_ankle', 'right_ankle', 'left_shoulder', 'right_shoulder',
                        'left_elbow', 'right_elbow', 'left_wrist', 'right_wrist']:
                for lm in result.landmarks:
                    if lm.get('name') == name and lm.get('visible'):
                        key_landmarks[name] = lm
                        break
            
            # Check if we have minimum landmarks for squat detection (at least legs)
            has_legs = all(key in key_landmarks for key in ['left_knee', 'right_knee', 'left_hip', 'right_hip'])
            detected_count = len(key_landmarks)
            
            # Update exercise state
            if has_legs and detected_count >= 6:  # Need at least 6 key points (relaxed from requiring all)
                state = exercise_detector.update(key_landmarks)
                
                # Draw exercise info (GREEN = good)
                y_offset = 35
                cv2.putText(display, f"Exercise: {state.exercise.value.upper()}", 
                           (15, y_offset), cv2.FONT_HERSHEY_SIMPLEX, 0.9, (0, 255, 0), 2)
                y_offset += 40
                
                # Stage color: GREEN for standing, YELLOW for transition, CYAN for down
                stage_colors = {
                    'standing': (0, 255, 0),      # Green
                    'transition': (0, 255, 255),  # Yellow
                    'down': (255, 200, 0)         # Cyan
                }
                stage_color = stage_colors.get(state.stage.value, (255, 255, 255))
                
                cv2.putText(display, f"Stage: {state.stage.value.upper()}", 
                           (15, y_offset), cv2.FONT_HERSHEY_SIMPLEX, 0.9, stage_color, 2)
                y_offset += 45
                
                # Rep count (BIG and GREEN)
                cv2.putText(display, f"REPS: {state.rep_count}", 
                           (15, y_offset), cv2.FONT_HERSHEY_SIMPLEX, 1.3, (0, 255, 0), 3)
                y_offset += 60
                
                # Draw feedback (RED = warnings/errors)
                if state.feedback_flags:
                    cv2.putText(display, "FEEDBACK:", 
                               (15, y_offset), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 100, 255), 2)
                    y_offset += 30
                    for feedback in state.feedback_flags[:3]:
                        cv2.putText(display, f"• {feedback}", 
                                   (15, y_offset), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 0, 255), 2)
                        y_offset += 28
                else:
                    # No feedback = Good form (GREEN)
                    cv2.putText(display, "✓ Good form!", 
                               (15, y_offset), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 255, 0), 2)
            else:
                # Not enough landmarks detected
                cv2.putText(display, f"Pose partial - {detected_count}/12 joints", 
                           (15, 35), cv2.FONT_HERSHEY_SIMPLEX, 0.8, (0, 255, 255), 2)
                cv2.putText(display, "Step back to show full body", 
                           (15, 70), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (255, 255, 255), 2)
        else:
            # NO POSE = RED warning
            cv2.putText(display, "NO POSE DETECTED", 
                       (15, 40), cv2.FONT_HERSHEY_SIMPLEX, 1.0, (0, 0, 255), 3)
            cv2.putText(display, "Stand in front of camera", 
                       (15, 80), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (255, 255, 255), 2)
            cv2.putText(display, "(full body visible)", 
                       (15, 110), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (255, 255, 255), 2)
        
        # FPS counter (top right, white)
        elapsed = time.time() - start_time
        fps = frame_count / elapsed if elapsed > 0 else 0
        cv2.putText(display, f"FPS: {fps:.1f}", 
                   (w - 140, 30), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (255, 255, 255), 2)
        
        # Latency (top right, green if <100ms, red if >100ms)
        latency_color = (0, 255, 0) if result.latency_ms < 100 else (0, 0, 255)
        cv2.putText(display, f"{result.latency_ms:.0f}ms", 
                   (w - 140, 60), cv2.FONT_HERSHEY_SIMPLEX, 0.7, latency_color, 2)
        
        # Landmarks count (bottom right)
        if result.detected:
            detected_count = len([lm for lm in result.landmarks if lm.get('visible', False)])
            lm_color = (0, 255, 0) if detected_count >= 20 else (0, 255, 255)
            cv2.putText(display, f"Joints: {detected_count}/33", 
                       (w - 180, h - 20), cv2.FONT_HERSHEY_SIMPLEX, 0.6, lm_color, 2)
        
        # Show frame
        cv2.imshow('Virtual Trainer', display)
        
        # Check for 'q' key
        key = cv2.waitKey(1) & 0xFF
        if key == ord('q'):
            print("\n👋 Quitting...")
            break
        elif key == ord('r'):
            # Reset rep counter
            exercise_detector = ExerciseDetector(exercise='squat')
            print("🔄 Rep counter reset")
    
    # Cleanup
    cap.release()
    cv2.destroyAllWindows()
    pose_detector.close()
    print("✅ Cleaned up")
    
    # Show final stats
    print(f"\n📊 Final Stats:")
    print(f"   Total frames: {frame_count}")
    print(f"   Average FPS: {fps:.1f}")
    print(f"   Duration: {elapsed:.1f}s")

if __name__ == '__main__':
    try:
        main()
    except KeyboardInterrupt:
        print("\n\n❌ Interrupted by user")
    except Exception as e:
        print(f"\n❌ Error: {e}")
        import traceback
        traceback.print_exc()
