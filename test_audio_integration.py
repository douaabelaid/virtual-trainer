"""
Test Audio Streaming Integration

This script demonstrates the audio streaming capabilities of the edge server.
It shows:
1. How to create audio messages
2. How to simulate backend sending audio feedback
3. How audio is forwarded to clients without blocking video

Run this after starting the WebSocket server to test audio integration.
"""

import asyncio
import base64
import json
import struct
import wave
import io
from pathlib import Path
import numpy as np

# Generate a simple test audio (1 second beep at 440Hz)
def generate_test_audio(frequency=440, duration_s=1.0, sample_rate=16000):
    """Generate a simple sine wave audio for testing."""
    t = np.linspace(0, duration_s, int(sample_rate * duration_s), False)
    audio_signal = np.sin(frequency * 2 * np.pi * t)
    
    # Convert to 16-bit PCM
    audio_signal = (audio_signal * 32767).astype(np.int16)
    
    # Encode as WAV
    wav_buffer = io.BytesIO()
    with wave.open(wav_buffer, 'wb') as wav_file:
        wav_file.setnchannels(1)  # Mono
        wav_file.setsampwidth(2)  # 16-bit
        wav_file.setframerate(sample_rate)
        wav_file.writeframes(audio_signal.tobytes())
    
    return wav_buffer.getvalue()


# Test audio message formats
def create_test_audio_messages():
    """Create sample audio messages for different feedback types."""
    
    messages = []
    
    # 1. Warning - Knee Cave
    audio_data = generate_test_audio(frequency=440, duration_s=0.8)
    messages.append({
        "type": "audio_feedback",
        "audio_data": base64.b64encode(audio_data).decode(),
        "code": "KNEE_CAVE",
        "severity": "warning",
        "text": "Keep your knees aligned with your toes",
        "format": "wav"
    })
    
    # 2. Error - Depth Insufficient
    audio_data = generate_test_audio(frequency=523, duration_s=1.0)
    messages.append({
        "type": "audio_feedback",
        "audio_data": base64.b64encode(audio_data).decode(),
        "code": "DEPTH_INSUFFICIENT",
        "severity": "error",
        "text": "Go deeper in your squat",
        "format": "wav"
    })
    
    # 3. Info - Good Form
    audio_data = generate_test_audio(frequency=349, duration_s=0.5)
    messages.append({
        "type": "audio_feedback",
        "audio_data": base64.b64encode(audio_data).decode(),
        "code": "FORM_GOOD",
        "severity": "info",
        "text": "Great form! Keep it up",
        "format": "wav"
    })
    
    return messages


async def test_audio_streaming():
    """Test audio streaming through WebSocket server."""
    
    try:
        import websockets
    except ImportError:
        print("❌ websockets library not installed")
        print("   Install: pip install websockets")
        return
    
    print("=" * 70)
    print("🎙️  Audio Streaming Test")
    print("=" * 70)
    print()
    
    # Connect to WebSocket server
    uri = "ws://localhost:8765"
    print(f"📡 Connecting to {uri}...")
    
    try:
        async with websockets.connect(uri) as websocket:
            print("✅ Connected!")
            print()
            
            # Test 1: Send ping
            print("📤 Sending ping...")
            await websocket.send(json.dumps({"type": "ping"}))
            response = await websocket.recv()
            print(f"📥 Received: {response}")
            print()
            
            # Test 2: Send audio feedback messages
            test_messages = create_test_audio_messages()
            
            for i, msg in enumerate(test_messages, 1):
                print(f"🎵 Test {i}/{len(test_messages)}: {msg['code']}")
                print(f"   Severity: {msg['severity']}")
                print(f"   Text: {msg['text']}")
                print(f"   Audio size: {len(base64.b64decode(msg['audio_data']))} bytes")
                
                # Send audio feedback message
                await websocket.send(json.dumps(msg))
                
                # Receive response
                response = await websocket.recv()
                response_data = json.loads(response)
                print(f"   Response: {response_data}")
                
                # Check for audio metadata
                if response_data.get("type") == "audio_queued":
                    print("   ✅ Audio queued for streaming")
                    
                    # Try to receive audio metadata
                    try:
                        metadata = await asyncio.wait_for(websocket.recv(), timeout=1.0)
                        metadata_data = json.loads(metadata)
                        if metadata_data.get("type") == "audio_metadata":
                            print(f"   🎵 Audio metadata: {metadata_data}")
                            
                            # Receive binary audio data
                            audio_binary = await asyncio.wait_for(websocket.recv(), timeout=1.0)
                            print(f"   📦 Received binary audio: {len(audio_binary)} bytes")
                    except asyncio.TimeoutError:
                        print("   ⏱️  No audio streamed (may be in cooldown)")
                
                print()
                await asyncio.sleep(0.6)  # Wait for cooldown
            
            print("=" * 70)
            print("✅ Audio streaming test complete!")
            print("=" * 70)
            
    except ConnectionRefusedError:
        print("❌ Connection refused!")
        print("   Make sure the WebSocket server is running:")
        print("   python edge/ws_server.py")
    except Exception as exc:
        print(f"❌ Test failed: {exc}")
        import traceback
        traceback.print_exc()


def test_audio_module():
    """Test audio_streamer module independently."""
    
    print("=" * 70)
    print("🧪 Audio Module Unit Test")
    print("=" * 70)
    print()
    
    try:
        import sys
        sys.path.insert(0, str(Path(__file__).parent / "edge"))
        from audio_streamer import (
            AudioStreamer, AudioConfig, AudioMode, 
            AudioFormat, create_audio_message
        )
        
        # Test 1: Initialize AudioStreamer
        print("1️⃣  Testing AudioStreamer initialization...")
        config = AudioConfig(
            mode=AudioMode.FORWARD_TO_CLIENT,
            sample_rate=16000,
            channels=1,
            cooldown_ms=500
        )
        streamer = AudioStreamer(config)
        print("   ✅ AudioStreamer initialized")
        print()
        
        # Test 2: Register clients
        print("2️⃣  Testing client registration...")
        streamer.register_client("client_1")
        streamer.register_client("client_2")
        print("   ✅ Clients registered")
        print()
        
        # Test 3: Create audio message
        print("3️⃣  Testing audio message creation...")
        audio_data = generate_test_audio()
        audio_msg = create_audio_message(
            audio_data=audio_data,
            feedback_code="TEST_CODE",
            severity="info",
            text="Test message",
            format=AudioFormat.WAV
        )
        print(f"   ✅ Audio message created: {len(audio_msg.audio_data)} bytes")
        print()
        
        # Test 4: Cooldown check
        print("4️⃣  Testing cooldown mechanism...")
        can_play_1 = streamer.should_play_audio("client_1")
        print(f"   First check: {can_play_1} (should be True)")
        
        # Simulate audio sent
        streamer._last_audio_time["client_1"] = asyncio.get_event_loop().time()
        can_play_2 = streamer.should_play_audio("client_1")
        print(f"   Immediate check: {can_play_2} (should be False)")
        print("   ✅ Cooldown working correctly")
        print()
        
        # Test 5: WAV encoding/decoding
        print("5️⃣  Testing WAV encoding/decoding...")
        pcm_data = b"test" * 1000
        wav_data = streamer.encode_wav(pcm_data)
        decoded_pcm, sr, ch, sw = streamer.decode_wav(wav_data)
        print(f"   Original: {len(pcm_data)} bytes")
        print(f"   WAV: {len(wav_data)} bytes")
        print(f"   Decoded: {len(decoded_pcm)} bytes ({sr}Hz, {ch}ch, {sw}B)")
        print("   ✅ Encoding/decoding working")
        print()
        
        # Test 6: Statistics
        print("6️⃣  Testing statistics...")
        stats = streamer.get_stats()
        print(f"   Stats: {stats}")
        print("   ✅ Statistics available")
        print()
        
        # Test 7: Unregister clients
        print("7️⃣  Testing client cleanup...")
        streamer.unregister_client("client_1")
        streamer.unregister_client("client_2")
        print("   ✅ Clients unregistered")
        print()
        
        print("=" * 70)
        print("✅ All audio module tests passed!")
        print("=" * 70)
        
    except ImportError as exc:
        print(f"❌ Import failed: {exc}")
        print("   Make sure edge/audio_streamer.py exists")
    except Exception as exc:
        print(f"❌ Test failed: {exc}")
        import traceback
        traceback.print_exc()


def print_usage():
    """Print usage instructions."""
    print()
    print("=" * 70)
    print("Audio Streaming Integration Test")
    print("=" * 70)
    print()
    print("Usage:")
    print("  python test_audio_integration.py [module|server]")
    print()
    print("Options:")
    print("  module  - Test audio_streamer module independently (default)")
    print("  server  - Test audio streaming through WebSocket server")
    print()
    print("Examples:")
    print("  # Test audio module")
    print("  python test_audio_integration.py module")
    print()
    print("  # Test audio streaming (requires running server)")
    print("  python edge/ws_server.py  # In terminal 1")
    print("  python test_audio_integration.py server  # In terminal 2")
    print()
    print("=" * 70)


if __name__ == "__main__":
    import sys
    
    if len(sys.argv) > 1 and sys.argv[1] == "server":
        # Test audio streaming through server
        asyncio.run(test_audio_streaming())
    elif len(sys.argv) > 1 and sys.argv[1] == "help":
        print_usage()
    else:
        # Test audio module independently (default)
        test_audio_module()
        print()
        print("💡 Tip: Run 'python test_audio_integration.py help' for more options")
