import cv2
import mediapipe as mp
import json
import time

# Initialize MediaPipe Pose
mp_pose = mp.solutions.pose
mp_drawing = mp.solutions.drawing_utils

def get_landmarks_json(landmarks, timestamp_ms):
    """Convert MediaPipe landmarks to JSON format"""
    landmark_data = {}
    for idx, landmark in enumerate(landmarks.landmark):
        landmark_data[mp_pose.PoseLandmark(idx).name] = {
            "x": round(landmark.x, 4),
            "y": round(landmark.y, 4),
            "z": round(landmark.z, 4),
            "visibility": round(landmark.visibility, 4)
        }
    return {
        "timestamp_ms": timestamp_ms,
        "landmarks": landmark_data
    }

def run():
    cap = cv2.VideoCapture(0)  # 0 = webcam

    with mp_pose.Pose(
        min_detection_confidence=0.5,
        min_tracking_confidence=0.5
    ) as pose:

        while cap.isOpened():
            ret, frame = cap.read()
            if not ret:
                break

            # Get timestamp
            timestamp_ms = int(time.time() * 1000)

            # Convert to RGB for MediaPipe
            image = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
            image.flags.writeable = False

            # Run pose detection
            results = pose.process(image)

            # Convert back to BGR for OpenCV
            image.flags.writeable = True
            image = cv2.cvtColor(image, cv2.COLOR_RGB2BGR)

            # Draw skeleton overlay
            if results.pose_landmarks:
                mp_drawing.draw_landmarks(
                    image,
                    results.pose_landmarks,
                    mp_pose.POSE_CONNECTIONS
                )

                # Print JSON to terminal
                data = get_landmarks_json(results.pose_landmarks, timestamp_ms)
                print(json.dumps(data))

            
            cv2.imshow('VPT - Pose Detector', image)

            
            if cv2.waitKey(10) & 0xFF == ord('q'):
                break

    cap.release()
    cv2.destroyAllWindows()

if __name__ == "__main__":
    run()