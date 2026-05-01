"""
Test script: STT connection flow with real speech audio.

Connects to STT directly (like noted client does), sends real speech audio,
and logs every event received. Verifies transcripts are received exactly once.

Run from agent_server container (has access to both networks):
  docker cp tests/test_stt_flow.py agent_server:/tmp/
  docker cp frontend/audio/user_message.wav agent_server:/tmp/
  docker exec agent_server python3 /tmp/test_stt_flow.py
"""

import asyncio
import socketio
import wave
import time

STT_URL = "http://stt_server:2700"
AGENT_URL = "http://agent_server:7701"
CLIENT_ID = f"test-stt-{int(time.time())}"
AUDIO_FILE = "/tmp/user_message.wav"

events_log = []


def log_event(source, event_name, data):
    entry = {
        "time": round(time.time(), 3),
        "source": source,
        "event": event_name,
        "data": str(data)[:200],
    }
    events_log.append(entry)
    print(f"  [{source:12s}] {event_name}: {str(data)[:150]}")


def load_wav(path):
    """Load WAV file as raw PCM16 bytes."""
    with wave.open(path, 'rb') as wf:
        assert wf.getsampwidth() == 2, f"Expected 16-bit, got {wf.getsampwidth()*8}-bit"
        assert wf.getnchannels() == 1, f"Expected mono, got {wf.getnchannels()} channels"
        rate = wf.getframerate()
        frames = wf.readframes(wf.getnframes())
        duration = wf.getnframes() / rate
        print(f"   Loaded {path}: {duration:.1f}s, {rate}Hz, {len(frames)} bytes")
        return frames, rate, duration


async def main():
    print(f"=== STT Flow Test (real speech) ===")
    print(f"CLIENT_ID: {CLIENT_ID}")
    print(f"STT_URL:   {STT_URL}")
    print(f"AGENT_URL: {AGENT_URL}")
    print()

    # Load audio
    print("0. Loading audio file...")
    audio_bytes, sample_rate, audio_duration = load_wav(AUDIO_FILE)

    # --- Connection 1: STT (direct, like noted client) ---
    stt_client = socketio.AsyncClient(logger=False)

    @stt_client.on('*')
    async def stt_catch_all(event, data):
        log_event("STT", event, data)

    @stt_client.on('connect')
    async def stt_connect():
        log_event("STT", "connect", "connected")

    @stt_client.on('transcription')
    async def stt_transcription(data):
        log_event("STT", "transcription", data)

    # --- Connection 2: agent_server (to monitor if it also receives transcripts) ---
    agent_client = socketio.AsyncClient(logger=False)

    @agent_client.on('*')
    async def agent_catch_all(event, data):
        log_event("AGENT_SERVER", event, data)

    @agent_client.on('connect')
    async def agent_connect():
        log_event("AGENT_SERVER", "connect", "connected")

    @agent_client.on('UserTranscript')
    async def agent_transcript(data):
        log_event("AGENT_SERVER", "UserTranscript", data)

    @agent_client.on('ChatChunk')
    async def agent_chat_chunk(data):
        log_event("AGENT_SERVER", "ChatChunk", data)

    @agent_client.on('ChatDone')
    async def agent_chat_done(data=None):
        log_event("AGENT_SERVER", "ChatDone", data)

    # --- Connect ---
    print("1. Connecting to STT...")
    try:
        await stt_client.connect(STT_URL, transports=['websocket'])
        print("   STT connected")
    except Exception as e:
        print(f"   STT connection failed: {e}")
        return

    print("2. Connecting to agent_server...")
    try:
        await agent_client.connect(AGENT_URL, transports=['websocket'])
        print("   agent_server connected")
    except Exception as e:
        print(f"   agent_server connection failed: {e}")
        await stt_client.disconnect()
        return

    await asyncio.sleep(0.5)

    # --- Test A: STT direct only (no JoinSTT) ---
    print()
    print("=== TEST A: Direct STT only (no agent_server subscription) ===")
    print("3. Sending audio to STT (no subscribe_transcripts, no JoinSTT)...")

    chunk_size = 3200  # 100ms at 16kHz, 16-bit
    for i in range(0, len(audio_bytes), chunk_size):
        chunk = audio_bytes[i:i + chunk_size]
        await stt_client.emit('audio_data', {
            'clientId': CLIENT_ID,
            'audioData': chunk,
        })
        await asyncio.sleep(0.05)

    # Send 1s of silence to trigger VAD end-of-speech
    silence = bytes(32000)  # 1s silence at 16kHz 16-bit
    await stt_client.emit('audio_data', {
        'clientId': CLIENT_ID,
        'audioData': silence,
    })

    print(f"4. Audio sent ({audio_duration:.1f}s + 1s silence). Waiting 8 seconds...")
    await asyncio.sleep(8.0)

    test_a_stt = [e for e in events_log if e['source'] == 'STT' and e['event'] == 'transcription']
    test_a_agent = [e for e in events_log if e['source'] == 'AGENT_SERVER' and e['event'] == 'UserTranscript']
    print(f"\n   TEST A Results:")
    print(f"   Transcripts on STT direct:    {len(test_a_stt)}")
    print(f"   Transcripts on agent_server:  {len(test_a_agent)}")
    for e in test_a_stt:
        print(f"   STT text: {e['data'][:150]}")

    # --- Summary ---
    print(f"\n=== Final Summary ===")
    all_transcripts = [e for e in events_log if e['event'] in ('transcription', 'UserTranscript')]
    print(f"Total transcript events: {len(all_transcripts)}")
    if len(all_transcripts) == 1:
        print("PASS: Exactly 1 transcript received")
    elif len(all_transcripts) == 0:
        print("FAIL: No transcripts received - STT may not have detected speech")
    else:
        print(f"FAIL: {len(all_transcripts)} transcripts received (expected 1) - DUPLICATE!")
        for e in all_transcripts:
            print(f"  [{e['source']}] {e['event']}: {e['data'][:100]}")

    # Cleanup
    await stt_client.disconnect()
    await agent_client.disconnect()
    print("\nDone.")


if __name__ == '__main__':
    asyncio.run(main())
