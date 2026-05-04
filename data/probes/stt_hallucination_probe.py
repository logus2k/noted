"""STT hallucination probe.

Pushes synthetic challenge audio through the FULL server-side STT pipeline
(server-side Silero VAD + Whisper) via Socket.IO — exactly the path the
noted client uses, just bypassing the browser VAD. The goal is to confirm
empirically whether the server-side Silero gate is doing its job, and to
catch any hallucination that escapes both gates.

Run from inside the agent_server container (it has python-socketio and is
on noted-network so it can reach stt_server:2700):

    docker cp data/probes/stt_hallucination_probe.py agent_server:/tmp/
    docker exec agent_server python3 /tmp/stt_hallucination_probe.py

Each test sends a different audio profile and waits a few seconds for STT
to either produce a `transcription` event or stay silent. Results print
inline.
"""

import asyncio
import math
import os
import struct
import time
import wave
from io import BytesIO

import socketio  # type: ignore

STT_URL = os.environ.get("STT_URL", "http://stt_server:2700")
SAMPLE_RATE = 16000


def make_pcm16_silence(duration_s: float) -> bytes:
    """N seconds of pure silence (zeros) as 16-bit mono PCM at 16 kHz."""
    n_samples = int(duration_s * SAMPLE_RATE)
    return b"\x00\x00" * n_samples


def make_pcm16_white_noise(duration_s: float, amplitude: float, seed: int = 42) -> bytes:
    """Low-amplitude white noise (PCM16). amplitude in [0,1] scales int16 max."""
    import random
    rng = random.Random(seed)
    n_samples = int(duration_s * SAMPLE_RATE)
    peak = int(32767 * amplitude)
    out = bytearray()
    for _ in range(n_samples):
        s = rng.randint(-peak, peak)
        out += struct.pack("<h", s)
    return bytes(out)


def make_pcm16_speech_band_tone(duration_s: float, freq: float = 220.0, amp: float = 0.05) -> bytes:
    """Pure sine in the male-voice fundamental band. Speech-band but not speech."""
    n_samples = int(duration_s * SAMPLE_RATE)
    peak = int(32767 * amp)
    out = bytearray()
    for i in range(n_samples):
        s = int(peak * math.sin(2 * math.pi * freq * i / SAMPLE_RATE))
        out += struct.pack("<h", s)
    return bytes(out)


async def run_one(label: str, audio_bytes: bytes) -> None:
    """Open a fresh STT socket, push the audio in 100ms chunks, wait, print result."""
    duration = len(audio_bytes) / 2 / SAMPLE_RATE
    client_id = f"probe-{label}-{int(time.time()*1000)}"
    transcripts: list[str] = []

    sio = socketio.AsyncClient()

    @sio.on("transcription")
    async def on_transcription(data):
        text = data.get("text") if isinstance(data, dict) else str(data)
        transcripts.append(text or "")

    try:
        await sio.connect(STT_URL, transports=["websocket"])
    except Exception as e:
        print(f"  [{label} {duration:.2f}s] STT connect failed: {e}", flush=True)
        return

    # Subscribe to this client_id so transcripts route back to us
    try:
        await sio.emit("subscribe_transcripts", {"clientId": client_id})
        await asyncio.sleep(0.2)
    except Exception:
        pass

    # Stream the audio in 100 ms chunks
    chunk_size = SAMPLE_RATE * 2 // 10  # 100ms PCM16
    for i in range(0, len(audio_bytes), chunk_size):
        await sio.emit("audio_data", {
            "clientId": client_id,
            "audioData": audio_bytes[i:i + chunk_size],
        })
        await asyncio.sleep(0.05)

    # Trailing 1s silence to flush VAD's end-of-speech detection
    silence_tail = make_pcm16_silence(1.0)
    for i in range(0, len(silence_tail), chunk_size):
        await sio.emit("audio_data", {
            "clientId": client_id,
            "audioData": silence_tail[i:i + chunk_size],
        })
        await asyncio.sleep(0.05)

    # Allow STT pipeline time to react
    await asyncio.sleep(4.0)

    await sio.disconnect()

    if transcripts:
        for t in transcripts:
            print(f"  [{label} {duration:.2f}s] HALLUCINATION? text={t!r}", flush=True)
    else:
        print(f"  [{label} {duration:.2f}s] (no transcript — VAD/STT correctly stayed silent)", flush=True)


async def main() -> None:
    print(f"=== STT hallucination probe — STT_URL={STT_URL} ===", flush=True)

    print("\n--- Pure silence (PCM16 zeros) ---", flush=True)
    for d in (0.6, 1.0, 2.0):
        await run_one(f"silence", make_pcm16_silence(d))

    print("\n--- Low-amplitude white noise (~ -60 dB FS) ---", flush=True)
    for d in (0.6, 1.0, 2.0):
        await run_one(f"noise60", make_pcm16_white_noise(d, amplitude=0.001))

    print("\n--- Higher noise (~ -45 dB FS) ---", flush=True)
    for d in (0.6, 1.0, 2.0):
        await run_one(f"noise45", make_pcm16_white_noise(d, amplitude=0.005))

    print("\n--- Speech-band tone (220 Hz, 0.05 amp) — in voice band but not speech ---", flush=True)
    for d in (0.6, 1.0, 2.0):
        await run_one(f"tone220", make_pcm16_speech_band_tone(d, freq=220.0, amp=0.05))

    print("\nDone.", flush=True)


if __name__ == "__main__":
    asyncio.run(main())
