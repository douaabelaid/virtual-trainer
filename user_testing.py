"""
user_testing.py - Real User Testing Framework

Connects to ws_server.py and logs detailed metrics for user testing sessions.
Tracks: rep accuracy, latency, landmark detection, feedback flags.

TWO MODES:
1. SERVER CAMERA MODE (default): ws_server.py captures from its own camera
2. CLIENT CAMERA MODE (--send-frames): This script captures and sends frames

Usage:
    # Mode 1: Server has the camera (user stands in front of server's webcam)
    python user_testing.py --user "User1" --height 170 --age 25 --sets 2 --reps 10

    # Mode 2: Client has the camera (this script captures your webcam)
    python user_testing.py --user "User1" --height 170 --age 25 --sets 2 --reps 10 --send-frames

    # Remote testing via ngrok
    python user_testing.py --user "User2" --height 165 --age 23 --sets 2 --reps 10 --send-frames --host ngrok-url --port 443 --ssl
"""

import asyncio
import argparse
import base64
import json
import logging
import time
from datetime import datetime
from typing import List, Dict, Any
import statistics

try:
    import cv2
except ImportError:
    cv2 = None

import websockets

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
)
logger = logging.getLogger("user_testing")


class TestingSession:
    """Tracks metrics for a single user testing session"""
    
    def __init__(self, user_name: str, height: int, age: int, exercise: str = "squat"):
        self.user_name = user_name
        self.height = height
        self.age = age
        self.exercise = exercise
        self.start_time = datetime.now()
        
        # Current set being recorded
        self.current_set = 0
        self.set_data: List[Dict[str, Any]] = []
        
        # Real-time metrics for current set
        self.set_start_rep = 0
        self.latencies: List[float] = []
        self.landmarks_detected_count = 0
        self.total_frames = 0
        self.feedback_flags: List[str] = []
        self.last_rep_count = 0
        
    def start_set(self, set_number: int, actual_reps: int):
        """Start recording a new set"""
        self.current_set = set_number
        self.set_start_rep = self.last_rep_count
        self.latencies = []
        self.landmarks_detected_count = 0
        self.total_frames = 0
        self.feedback_flags = []
        logger.info(f"\n{'='*60}")
        logger.info(f"SET {set_number} STARTED - Perform {actual_reps} reps now!")
        logger.info(f"{'='*60}\n")
    
    def record_frame(self, data: dict):
        """Record metrics from a single frame"""
        self.total_frames += 1
        
        # Track latency
        if 'latency_ms' in data:
            self.latencies.append(data['latency_ms'])
        
        # Track landmark detection
        if data.get('landmarks') and len(data['landmarks']) > 0:
            self.landmarks_detected_count += 1
        
        # Track feedback flags
        if data.get('feedback') and len(data['feedback']) > 0:
            for flag in data['feedback']:
                if flag not in self.feedback_flags:
                    self.feedback_flags.append(flag)
        
        # Update rep count
        if 'rep_count' in data:
            self.last_rep_count = data['rep_count']
        
        # Real-time display
        stage = data.get('stage', 'unknown')
        reps_in_set = self.last_rep_count - self.set_start_rep
        current_latency = data.get('latency_ms', 0)
        
        # Print update every 10 frames to avoid spam
        if self.total_frames % 10 == 0:
            logger.info(f"Set {self.current_set} | Reps: {reps_in_set} | "
                       f"Stage: {stage:12s} | Latency: {current_latency:5.1f}ms | "
                       f"Landmarks: {'✓' if data.get('landmarks') else '✗'}")
    
    def end_set(self, actual_reps: int):
        """Finalize current set and save statistics"""
        reps_counted = self.last_rep_count - self.set_start_rep
        
        # Calculate metrics
        mean_latency = statistics.mean(self.latencies) if self.latencies else 0
        max_latency = max(self.latencies) if self.latencies else 0
        any_latency_over_100 = any(l > 100 for l in self.latencies)
        landmarks_detection_rate = (self.landmarks_detected_count / self.total_frames * 100) if self.total_frames > 0 else 0
        rep_accuracy = (reps_counted / actual_reps * 100) if actual_reps > 0 else 0
        
        set_result = {
            'set_number': self.current_set,
            'actual_reps': actual_reps,
            'reps_counted': reps_counted,
            'rep_accuracy': rep_accuracy,
            'mean_latency': mean_latency,
            'max_latency': max_latency,
            'any_latency_over_100': any_latency_over_100,
            'landmarks_detection_rate': landmarks_detection_rate,
            'feedback_flags': self.feedback_flags.copy(),
            'total_frames': self.total_frames,
        }
        
        self.set_data.append(set_result)
        
        # Print set summary
        logger.info(f"\n{'='*60}")
        logger.info(f"SET {self.current_set} COMPLETED")
        logger.info(f"{'='*60}")
        logger.info(f"Actual reps performed:     {actual_reps}")
        logger.info(f"Reps counted by system:    {reps_counted}")
        logger.info(f"Rep accuracy:              {rep_accuracy:.1f}%")
        logger.info(f"Mean latency:              {mean_latency:.1f} ms")
        logger.info(f"Max latency:               {max_latency:.1f} ms")
        logger.info(f"Any latency > 100ms:       {'YES' if any_latency_over_100 else 'NO'}")
        logger.info(f"Landmark detection rate:   {landmarks_detection_rate:.1f}%")
        logger.info(f"Feedback flags triggered:  {', '.join(self.feedback_flags) if self.feedback_flags else 'None'}")
        logger.info(f"{'='*60}\n")
        
        return set_result
    
    def generate_report(self) -> dict:
        """Generate complete testing report"""
        # Calculate overall statistics
        total_actual = sum(s['actual_reps'] for s in self.set_data)
        total_counted = sum(s['reps_counted'] for s in self.set_data)
        overall_accuracy = (total_counted / total_actual * 100) if total_actual > 0 else 0
        
        all_mean_latencies = [s['mean_latency'] for s in self.set_data]
        avg_mean_latency = statistics.mean(all_mean_latencies) if all_mean_latencies else 0
        
        all_feedback = []
        for s in self.set_data:
            all_feedback.extend(s['feedback_flags'])
        unique_feedback = list(set(all_feedback))
        
        report = {
            'user_info': {
                'name': self.user_name,
                'height_cm': self.height,
                'age': self.age,
                'date_time': self.start_time.strftime('%Y-%m-%d %H:%M:%S'),
                'exercise': self.exercise,
            },
            'sets': self.set_data,
            'summary': {
                'total_actual_reps': total_actual,
                'total_counted_reps': total_counted,
                'overall_rep_accuracy': overall_accuracy,
                'average_mean_latency': avg_mean_latency,
                'meets_90_percent_target': overall_accuracy >= 90,
                'latency_under_100ms': avg_mean_latency < 100,
                'all_feedback_flags': unique_feedback,
            }
        }
        
        return report
    
    def print_final_report(self):
        """Print formatted final report"""
        report = self.generate_report()
        
        print("\n" + "="*80)
        print(f"TESTING SESSION COMPLETE - {self.user_name}")
        print("="*80)
        print(f"\nUser Information:")
        print(f"  Name:           {report['user_info']['name']}")
        print(f"  Height:         {report['user_info']['height_cm']} cm")
        print(f"  Age:            {report['user_info']['age']}")
        print(f"  Date/Time:      {report['user_info']['date_time']}")
        print(f"  Exercise:       {report['user_info']['exercise']}")
        
        print(f"\nSet-by-Set Results:")
        print(f"  {'Metric':<30} {'Set 1':>10} {'Set 2':>10}")
        print(f"  {'-'*30} {'-'*10} {'-'*10}")
        
        if len(self.set_data) >= 1:
            s1 = self.set_data[0]
            s2 = self.set_data[1] if len(self.set_data) >= 2 else None
            
            print(f"  {'Actual reps performed':<30} {s1['actual_reps']:>10} {s2['actual_reps']:>10 if s2 else 'N/A':>10}")
            print(f"  {'Reps counted by system':<30} {s1['reps_counted']:>10} {s2['reps_counted']:>10 if s2 else 'N/A':>10}")
            print(f"  {'Rep accuracy (%)':<30} {s1['rep_accuracy']:>10.1f} {s2['rep_accuracy']:>10.1f if s2 else 'N/A':>10}")
            print(f"  {'Mean latency (ms)':<30} {s1['mean_latency']:>10.1f} {s2['mean_latency']:>10.1f if s2 else 'N/A':>10}")
            print(f"  {'Max latency (ms)':<30} {s1['max_latency']:>10.1f} {s2['max_latency']:>10.1f if s2 else 'N/A':>10}")
            print(f"  {'Any latency > 100ms?':<30} {'YES' if s1['any_latency_over_100'] else 'NO':>10} {('YES' if s2['any_latency_over_100'] else 'NO'):>10 if s2 else 'N/A':>10}")
            print(f"  {'Landmarks detected?':<30} {'YES':>10} {'YES':>10 if s2 else 'N/A':>10}")
        
        print(f"\nOverall Summary:")
        print(f"  Total reps (actual):       {report['summary']['total_actual_reps']}")
        print(f"  Total reps (counted):      {report['summary']['total_counted_reps']}")
        print(f"  Overall rep accuracy:      {report['summary']['overall_rep_accuracy']:.1f}%")
        print(f"  Average mean latency:      {report['summary']['average_mean_latency']:.1f} ms")
        print(f"  Meets 90% target:          {'✓ YES' if report['summary']['meets_90_percent_target'] else '✗ NO'}")
        print(f"  Latency under 100ms:       {'✓ YES' if report['summary']['latency_under_100ms'] else '✗ NO'}")
        print(f"  Feedback flags:            {', '.join(report['summary']['all_feedback_flags']) if report['summary']['all_feedback_flags'] else 'None'}")
        
        print("="*80 + "\n")
        
        # Save to JSON file
        filename = f"user_test_{self.user_name.replace(' ', '_')}_{self.start_time.strftime('%Y%m%d_%H%M%S')}.json"
        with open(filename, 'w') as f:
            json.dump(report, f, indent=2)
        logger.info(f"Report saved to: {filename}")
        
        return report


async def run_testing_session(
    uri: str, 
    user_name: str, 
    height: int, 
    age: int, 
    exercise: str,
    sets: int, 
    reps_per_set: int,
    send_frames: bool = False,
    fps: int = 15
):
    """Main testing session loop - supports both server camera and client camera modes"""
    
    session = TestingSession(user_name, height, age, exercise)
    
    logger.info(f"\n{'='*80}")
    logger.info(f"USER TESTING SESSION")
    logger.info(f"{'='*80}")
    logger.info(f"User:     {user_name}")
    logger.info(f"Height:   {height} cm")
    logger.info(f"Age:      {age}")
    logger.info(f"Exercise: {exercise}")
    logger.info(f"Sets:     {sets} sets of {reps_per_set} reps each")
    logger.info(f"Mode:     {'CLIENT CAMERA (sending frames)' if send_frames else 'SERVER CAMERA (receiving only)'}")
    logger.info(f"{'='*80}\n")
    
    # Setup camera if in send-frames mode
    cap = None
    if send_frames:
        if cv2 is None:
            logger.error("✗ opencv-python not installed. Install with: pip install opencv-python")
            return
        cap = cv2.VideoCapture(0)
        if not cap.isOpened():
            logger.error("✗ Cannot open camera. Check webcam connection.")
            return
        cap.set(cv2.CAP_PROP_FRAME_WIDTH, 640)
        cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 480)
        logger.info("✓ Camera opened for frame sending")
        frame_interval = 1.0 / fps
    
    logger.info(f"Connecting to {uri} ...")
    
    try:
        async with websockets.connect(uri) as ws:
            logger.info(f"✓ Connected to server")
            
            # Set exercise
            await ws.send(json.dumps({"type": "set_exercise", "exercise": exercise}))
            logger.info(f"✓ Exercise set to: {exercise}\n")
            
            # Setup frame sending task if needed
            send_task = None
            if send_frames:
                async def send_frames_task():
                    """Continuously capture and send frames"""
                    while True:
                        t0 = time.monotonic()
                        ret, frame = cap.read()
                        if not ret:
                            await asyncio.sleep(frame_interval)
                            continue
                        
                        # Encode to JPEG then base64
                        _, buf = cv2.imencode(".jpg", frame, [cv2.IMWRITE_JPEG_QUALITY, 80])
                        b64 = base64.b64encode(buf).decode()
                        
                        payload = json.dumps({
                            "type": "frame",
                            "data": b64,
                            "exercise": exercise
                        }, separators=(",", ":"))
                        
                        await ws.send(payload)
                        
                        # Maintain FPS
                        elapsed = time.monotonic() - t0
                        sleep_for = frame_interval - elapsed
                        if sleep_for > 0:
                            await asyncio.sleep(sleep_for)
                
                send_task = asyncio.create_task(send_frames_task())
                logger.info("✓ Frame sending started")
            
            # Wait for user to get ready
            input("Press ENTER when ready to start SET 1...")
            session.start_set(1, reps_per_set)
            
            current_set = 1
            set_started = True
            
            while True:
                try:
                    # Receive data from server
                    message = await asyncio.wait_for(ws.recv(), timeout=5.0)
                    data = json.loads(message)
                    
                    # Handle heartbeat messages (camera working but no pose detected)
                    if data.get("type") == "heartbeat":
                        logger.info(f"⚠️  {data.get('message', 'No pose detected')}")
                        continue
                    
                    # Skip other non-pose messages
                    if data.get("type") and data.get("type") != "pose":
                        continue
                    
                    # Record frame metrics
                    session.record_frame(data)
                    
                    # Check if we've completed the target reps for this set
                    reps_in_set = session.last_rep_count - session.set_start_rep
                    
                    if set_started and reps_in_set >= reps_per_set:
                        # Set complete
                        session.end_set(reps_per_set)
                        set_started = False
                        current_set += 1
                        
                        if current_set <= sets:
                            # Start next set
                            input(f"\nPress ENTER when ready to start SET {current_set}...")
                            session.start_set(current_set, reps_per_set)
                            set_started = True
                        else:
                            # All sets complete
                            logger.info("\n✓ All sets completed!")
                            break
                    
                except asyncio.TimeoutError:
                    logger.warning("No data received in 5s - is the camera working?")
                    continue
                except json.JSONDecodeError:
                    logger.warning(f"Invalid JSON received: {message}")
                    continue
            
            # Cancel frame sending task if it exists
            if send_task:
                send_task.cancel()
            
            # Generate final report
            session.print_final_report()
            
    except websockets.exceptions.WebSocketException as e:
        logger.error(f"WebSocket error: {e}")
        logger.error("Make sure ws_server.py is running!")
    except KeyboardInterrupt:
        logger.info("\n✗ Session interrupted by user")
        if session.set_data:
            session.print_final_report()
    except Exception as e:
        logger.error(f"Error: {e}", exc_info=True)
    finally:
        if cap:
            cap.release()
            logger.info("Camera released")


def main():
    parser = argparse.ArgumentParser(description='User Testing Framework for Virtual Trainer')
    parser.add_argument('--user', type=str, required=True, help='User name or initials')
    parser.add_argument('--height', type=int, required=True, help='User height in cm')
    parser.add_argument('--age', type=int, required=True, help='User age')
    parser.add_argument('--exercise', type=str, default='squat', choices=['squat', 'lunge', 'pushup'],
                       help='Exercise to test (default: squat)')
    parser.add_argument('--sets', type=int, default=2, help='Number of sets (default: 2)')
    parser.add_argument('--reps', type=int, default=10, help='Reps per set (default: 10)')
    parser.add_argument('--host', type=str, default='127.0.0.1', help='WebSocket server host')
    parser.add_argument('--port', type=int, default=8000, help='WebSocket server port')
    parser.add_argument('--ssl', action='store_true', help='Use wss:// instead of ws://')
    parser.add_argument('--send-frames', action='store_true', 
                       help='Capture from local camera and send frames to server (default: receive from server camera)')
    parser.add_argument('--fps', type=int, default=15, help='Frame rate when sending frames (default: 15)')
    
    args = parser.parse_args()
    
    # Build WebSocket URI
    protocol = 'wss' if args.ssl else 'ws'
    uri = f"{protocol}://{args.host}:{args.port}/ws"
    
    # Run testing session
    asyncio.run(run_testing_session(
        uri=uri,
        user_name=args.user,
        height=args.height,
        age=args.age,
        exercise=args.exercise,
        sets=args.sets,
        reps_per_set=args.reps,
        send_frames=args.send_frames,
        fps=args.fps
    ))


if __name__ == '__main__':
    main()
