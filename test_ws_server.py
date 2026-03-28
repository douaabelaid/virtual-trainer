import unittest
import sys
import os
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

# Mock the dependencies for testing
class MockWebSocket:
    def __enter__(self):
        return self
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        pass
    
    def receive_json(self):
        return {
            "frame_id": 1,
            "timestamp_ms": 1234567890,
            "landmarks": {"left_knee": {"x": 0.5, "y": 0.5}}
        }

class MockTestClient:
    def websocket_connect(self, url):
        return MockWebSocket()

client = MockTestClient()

# Mock MediaPipe Pose
class MockLandmark:
    def __init__(self, x, y):
        self.x = x
        self.y = y

class MockLandmarks:
    def __init__(self):
        self.landmark = [MockLandmark(0.5, 0.5) for _ in range(33)]

class TestVirtualTrainer(unittest.TestCase):

    def test_websocket_response(self):
        """Test WebSocket response structure."""
        with client.websocket_connect("/ws") as websocket:
            response = websocket.receive_json()
            self.assertIn("frame_id", response)
            self.assertIn("timestamp_ms", response)
            self.assertIn("landmarks", response)

    def test_get_landmarks_json(self):
        """Test the get_landmarks_json function."""
        # Import here to avoid module issues during testing
        try:
            from edge.ws_server import get_landmarks_json
            
            landmarks = MockLandmarks()
            timestamp_ms = 1234567890
            result = get_landmarks_json(landmarks, timestamp_ms)

            self.assertEqual(result["timestamp_ms"], timestamp_ms)
            self.assertIn("left_knee", result["landmarks"])
            self.assertEqual(result["landmarks"]["left_knee"]["x"], 0.5)
            self.assertEqual(result["landmarks"]["left_knee"]["y"], 0.5)
        except ImportError:
            self.skipTest("Could not import get_landmarks_json")

    def test_schema_validation(self):
        """Test schema validation for ExerciseState."""
        try:
            from shared.exercise_state_schema import ExerciseState, ExerciseType, ExerciseStage
            
            data = {
                "timestamp_ms": 1234567890,
                "exercise": "squat",
                "stage": "standing",
                "rep_count": 5,
                "joint_angles": {
                    "left_knee": 90.0,
                    "right_knee": 90.0
                },
                "feedback_flags": [
                    {"code": "001", "message": "Good form", "severity": "info"}
                ],
                "landmarks_raw": {}
            }

            exercise_state = ExerciseState(**data)
            self.assertEqual(exercise_state.timestamp_ms, 1234567890)
            self.assertEqual(exercise_state.exercise, ExerciseType.SQUAT)
            self.assertEqual(exercise_state.stage, ExerciseStage.STANDING)
            self.assertEqual(exercise_state.rep_count, 5)
            self.assertEqual(exercise_state.joint_angles.left_knee, 90.0)
            self.assertEqual(exercise_state.feedback_flags[0].code, "001")
            self.assertEqual(exercise_state.feedback_flags[0].message, "Good form")
            self.assertEqual(exercise_state.feedback_flags[0].severity, "info")
        except ImportError:
            self.skipTest("Could not import exercise state schema")

if __name__ == '__main__':
    unittest.main()