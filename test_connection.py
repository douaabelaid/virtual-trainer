"""
test_connection.py - Quick connection test for user testing setup

Verifies WebSocket connection and basic functionality before starting user tests.

TWO MODES:
1. SERVER CAMERA MODE (default): Receives frames from server's camera
2. CLIENT CAMERA MODE (--send-frames): Captures and sends frames to server

Usage:
    python test_connection.py
    python test_connection.py --send-frames
    python test_connection.py --send-frames --host ngrok-url --port 443 --ssl
"""

import asyncio
import argparse
import base64
import json
import logging
import sys
import time

try:
    import cv2
except ImportError:
    cv2 = None

import websockets

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
)
logger = logging.getLogger("test_connection")


async def test_connection(uri: str, send_frames: bool = False):
    """Test WebSocket connection and basic communication"""
    
    print("\n" + "="*60)
    print("CONNECTION TEST")
    print("="*60)
    print(f"Mode: {'CLIENT CAMERA (sending frames)' if send_frames else 'SERVER CAMERA (receiving only)'}")
    print("="*60 + "\n")
    
    # Setup camera if sending frames
    cap = None
    if send_frames:
        if cv2 is None:
            logger.error("✗ opencv-python not installed")
            logger.error("  Install with: pip install opencv-python")
            return False
        cap = cv2.VideoCapture(0)
        if not cap.isOpened():
            logger.error("✗ Cannot open camera")
            logger.error("  Check webcam connection")
            return False
        cap.set(cv2.CAP_PROP_FRAME_WIDTH, 640)
        cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 480)
        logger.info("✓ Camera opened successfully")
    
    try:
        # Test 1: Connection
        logger.info(f"\nTest 1: Connecting to {uri} ...")
        start = time.time()
        
        async with websockets.connect(uri, ping_interval=20, ping_timeout=10) as ws:
            connect_time = (time.time() - start) * 1000
            logger.info(f"✓ Connected successfully in {connect_time:.1f}ms")
            
            # Test 2: Set exercise
            logger.info("\nTest 2: Setting exercise to 'squat' ...")
            await ws.send(json.dumps({"type": "set_exercise", "exercise": "squat"}))
            logger.info("✓ Exercise command sent")
            
            # Start frame sending task if needed
            send_task = None
            if send_frames:
                logger.info("\nTest 3: Starting frame capture and send ...")
                
                async def send_frames_task():
                    """Send frames continuously"""
                    frame_count = 0
                    while frame_count < 100:  # Send 100 frames for test
                        ret, frame = cap.read()
                        if not ret:
                            await asyncio.sleep(0.01)
                            continue
                        
                        # Encode to JPEG
                        _, buf = cv2.imencode(".jpg", frame, [cv2.IMWRITE_JPEG_QUALITY, 80])
                        b64 = base64.b64encode(buf).decode()
                        
                        payload = json.dumps({
                            "type": "frame",
                            "data": b64,
                            "exercise": "squat"
                        }, separators=(",", ":"))
                        
                        await ws.send(payload)
                        frame_count += 1
                        await asyncio.sleep(1/15)  # 15 FPS
                
                send_task = asyncio.create_task(send_frames_task())
                logger.info("✓ Frame sending started")
            
            # Test 3/4: Receive data
            test_num = 4 if send_frames else 3
            logger.info(f"\nTest {test_num}: Waiting for server data (5 seconds) ...")
            frames_received = 0
            latencies = []
            landmarks_ok = 0
            
            try:
                start_test = time.time()
                while time.time() - start_test < 5.0:
                    try:
                        message = await asyncio.wait_for(ws.recv(), timeout=1.0)
                        data = json.loads(message)
                        
                        # Skip non-pose messages
                        if data.get("type") and data.get("type") != "pose":
                            continue
                        
                        frames_received += 1
                        
                        if 'latency_ms' in data:
                            latencies.append(data['latency_ms'])
                        
                        if data.get('landmarks') and len(data['landmarks']) > 0:
                            landmarks_ok += 1
                        
                        # Print first frame as sample
                        if frames_received == 1:
                            logger.info(f"✓ Received first frame:")
                            logger.info(f"  - Exercise: {data.get('exercise', 'N/A')}")
                            logger.info(f"  - Stage: {data.get('stage', 'N/A')}")
                            logger.info(f"  - Latency: {data.get('latency_ms', 'N/A')} ms")
                            logger.info(f"  - Landmarks: {len(data.get('landmarks', []))} detected")
                    
                    except asyncio.TimeoutError:
                        continue
                    except json.JSONDecodeError:
                        logger.warning("Received invalid JSON")
                        continue
            
            except Exception as e:
                logger.error(f"Error during data reception: {e}")
            
            # Cancel send task if active
            if send_task:
                send_task.cancel()
            
            # Summary
            print("\n" + "-"*60)
            print("TEST RESULTS")
            print("-"*60)
            print(f"Frames received:       {frames_received}")
            print(f"Frames with landmarks: {landmarks_ok}")
            
            if latencies:
                avg_latency = sum(latencies) / len(latencies)
                max_latency = max(latencies)
                print(f"Average latency:       {avg_latency:.1f} ms")
                print(f"Max latency:           {max_latency:.1f} ms")
                
                if avg_latency < 100:
                    print("✓ Latency OK (< 100ms)")
                else:
                    print("✗ Latency HIGH (≥ 100ms)")
            
            if frames_received > 0:
                landmark_rate = (landmarks_ok / frames_received) * 100
                print(f"Landmark detection:    {landmark_rate:.1f}%")
                
                if landmark_rate > 80:
                    print("✓ Landmark detection OK")
                else:
                    print("⚠ Landmark detection LOW - check camera setup")
            
            print("-"*60)
            
            # Overall status
            print("\nOVERALL STATUS:")
            
            all_good = True
            
            if frames_received < 5:
                print("✗ Not enough frames received - check camera/setup")
                if not send_frames:
                    print("  TIP: Try --send-frames mode to use YOUR webcam")
                all_good = False
            else:
                print("✓ Receiving frames")
            
            if latencies and avg_latency < 100:
                print("✓ Latency within target")
            elif latencies:
                print("⚠ Latency above target")
                all_good = False
            else:
                print("⚠ No latency data received")
                all_good = False
            
            if landmarks_ok > 0:
                print("✓ Landmarks detected")
            else:
                print("✗ No landmarks detected - position user in camera view")
                all_good = False
            
            print("\n" + "="*60)
            
            if all_good:
                print("✓ ALL TESTS PASSED - Ready for user testing!")
            else:
                print("⚠ SOME ISSUES DETECTED - Review above before testing")
            
            print("="*60 + "\n")
            
            return all_good
    
    except websockets.exceptions.InvalidStatusCode as e:
        logger.error(f"✗ Connection failed: {e}")
        logger.error("  Check that ws_server.py is running")
        return False
    
    except websockets.exceptions.WebSocketException as e:
        logger.error(f"✗ WebSocket error: {e}")
        logger.error("  Check server address and network connection")
        return False
    
    except ConnectionRefusedError:
        logger.error("✗ Connection refused")
        logger.error("  Make sure ws_server.py is running on the correct port")
        return False
    
    except Exception as e:
        logger.error(f"✗ Unexpected error: {e}")
        return False
    
    finally:
        if cap:
            cap.release()


def main():
    parser = argparse.ArgumentParser(description='Test WebSocket connection for user testing')
    parser.add_argument('--host', type=str, default='127.0.0.1', 
                       help='WebSocket server host (default: 127.0.0.1)')
    parser.add_argument('--port', type=int, default=8000, 
                       help='WebSocket server port (default: 8000)')
    parser.add_argument('--ssl', action='store_true', 
                       help='Use wss:// instead of ws://')
    parser.add_argument('--send-frames', action='store_true',
                       help='Capture from local camera and send frames to server')
    
    args = parser.parse_args()
    
    # Build URI
    protocol = 'wss' if args.ssl else 'ws'
    uri = f"{protocol}://{args.host}:{args.port}/ws"
    
    # Run test
    result = asyncio.run(test_connection(uri, send_frames=args.send_frames))
    
    # Exit code for scripting
    sys.exit(0 if result else 1)


if __name__ == '__main__':
    main()
