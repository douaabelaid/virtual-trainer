"""
Quick test to verify ws_server webcam connection works
Usage: python test_server_connection.py
"""
import asyncio
import json
import websockets

async def test_connection():
    uri = "ws://127.0.0.1:8000/ws"
    print(f"Connecting to {uri}...")
    
    try:
        async with websockets.connect(uri) as ws:
            print("✅ Connected successfully!")
            print("Waiting for pose data from server's webcam...")
            print("(Stand in front of the server's camera)\n")
            
            frame_count = 0
            for _ in range(30):  # Receive 30 frames (~2 seconds at 15 FPS)
                message = await asyncio.wait_for(ws.recv(), timeout=5.0)
                data = json.loads(message)
                
                frame_count += 1
                
                # Display status
                stage = data.get('stage', 'unknown')
                reps = data.get('rep_count', 0)
                latency = data.get('latency_ms', 0)
                fps = data.get('fps', 0)
                landmarks = len(data.get('landmarks', {}))
                
                print(f"Frame {frame_count:3d} | "
                      f"Stage: {stage:12s} | "
                      f"Reps: {reps:2d} | "
                      f"Landmarks: {landmarks:2d} | "
                      f"FPS: {fps:5.1f} | "
                      f"Latency: {latency:5.1f} ms")
            
            print("\n✅ Test successful! Server is streaming pose data correctly.")
            print(f"   Received {frame_count} frames with pose data.")
            
    except asyncio.TimeoutError:
        print("❌ Timeout: No data received from server.")
        print("   Make sure someone is visible in the camera!")
    except websockets.exceptions.WebSocketException as e:
        print(f"❌ WebSocket error: {e}")
        print("   Make sure ws_server.py is running!")
    except Exception as e:
        print(f"❌ Error: {e}")

if __name__ == '__main__':
    asyncio.run(test_connection())
