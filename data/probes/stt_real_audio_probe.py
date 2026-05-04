"""STT real-audio reproducer probe.

Pushes one or more REAL captured WAV files through the full server-side
STT pipeline (Silero VAD + Whisper) via Socket.IO — same path the noted
client uses, just bypassing the browser. Lets us deterministically
reproduce the hallucinations that captured WAVs in
~/env/assets/stt_server/data/captures/ originally produced.

Differs from `stt_hallucination_probe.py`, which generates synthetic
silence/noise/tones. This one replays known-bad recordings so we can
verify pipeline changes against ground-truth failure cases.

Usage from inside the agent_server container (which has python-socketio
and is on noted-network so it can reach stt_server:2700):

    # copy probe + WAVs in
    docker cp data/probes/stt_real_audio_probe.py agent_server:/tmp/
    docker cp ~/env/assets/stt_server/data/captures/20260504_032933_366_0.80s.wav agent_server:/tmp/
    docker cp ~/env/assets/stt_server/data/captures/20260504_033626_323_0.44s.wav agent_server:/tmp/

    # run it
    docker exec agent_server python3 /tmp/stt_real_audio_probe.py \
        /tmp/20260504_032933_366_0.80s.wav \
        /tmp/20260504_033626_323_0.44s.wav

The probe streams each WAV in 100 ms chunks (matching the noted client's
packetisation), pads with 1 s of trailing silence so the VAD's
end-of-speech timer fires, then waits a few seconds for any transcript.
Prints WAV stats + result inline.
"""

import asyncio
import math
import os
import sys
import time
import wave
from pathlib import Path

import socketio  # type: ignore

STT_URL = os.environ.get("STT_URL", "http://stt_server:2700")
SAMPLE_RATE = 16000
CHUNK_MS = 100
CHUNK_BYTES = SAMPLE_RATE * 2 * CHUNK_MS // 1000   # 100 ms PCM16
TRAIL_SILENCE_S = 1.0
WAIT_FOR_TRANSCRIPT_S = 5.0


def load_pcm16_from_wav(path: Path) -> tuple[bytes, float, dict]:
    """Read a 16-bit mono 16 kHz WAV. Return (raw_pcm, duration_s, stats)."""
    with wave.open(str(path), "rb") as w:
        n = w.getnframes()
        sr = w.getframerate()
        ch = w.getnchannels()
        sw = w.getsampwidth()
        raw = w.readframes(n)
    if sr != SAMPLE_RATE or ch != 1 or sw != 2:
        raise ValueError(
            f"{path.name}: expected mono 16-bit 16kHz; got "
            f"sr={sr} ch={ch} sw={sw}"
        )
    duration = n / sr
    # Quick amplitude sanity for the report.
    import struct
    samples = struct.unpack(f"<{n}h", raw)
    rms_int = math.sqrt(sum(s * s for s in samples) / max(n, 1))
    rms_db = 20 * math.log10((rms_int / 32768.0) + 1e-12)
    peak_int = max((abs(s) for s in samples), default=0)
    peak_db = 20 * math.log10((peak_int / 32768.0) + 1e-12)
    return raw, duration, {"rms_db": rms_db, "peak_db": peak_db, "n_samples": n}


async def run_one(wav_path: Path) -> None:
    raw_pcm, duration, stats = load_pcm16_from_wav(wav_path)
    label = wav_path.name
    print(
        f"\n=== {label} ===  duration={duration:.2f}s  "
        f"rms={stats['rms_db']:.1f}dB  peak={stats['peak_db']:.1f}dB",
        flush=True,
    )

    client_id = f"realprobe-{int(time.time() * 1000)}"
    transcripts: list[str] = []

    sio = socketio.AsyncClient()

    @sio.on("transcription")
    async def on_transcription(data):
        text = data.get("text") if isinstance(data, dict) else str(data)
        transcripts.append(text or "")

    try:
        await sio.connect(STT_URL, transports=["websocket"])
    except Exception as e:
        print(f"  STT connect failed: {e}", flush=True)
        return

    try:
        await sio.emit("subscribe_transcripts", {"clientId": client_id})
        await asyncio.sleep(0.2)

        # Stream the actual recorded audio in 100 ms chunks.
        for i in range(0, len(raw_pcm), CHUNK_BYTES):
            await sio.emit("audio_data", {
                "clientId": client_id,
                "audioData": raw_pcm[i:i + CHUNK_BYTES],
            })
            await asyncio.sleep(0.05)  # half real-time keeps server fed without flooding

        # Pad with trailing silence so VAD declares end-of-speech.
        silence_chunk = b"\x00\x00" * (SAMPLE_RATE * CHUNK_MS // 1000)
        for _ in range(int(TRAIL_SILENCE_S * 1000 / CHUNK_MS)):
            await sio.emit("audio_data", {
                "clientId": client_id,
                "audioData": silence_chunk,
            })
            await asyncio.sleep(0.05)

        # Give the pipeline time to react.
        await asyncio.sleep(WAIT_FOR_TRANSCRIPT_S)
    finally:
        await sio.disconnect()

    if transcripts:
        for t in transcripts:
            print(f"  >>> TRANSCRIPT: {t!r}", flush=True)
    else:
        print("  >>> (no transcript — VAD/STT correctly stayed silent)", flush=True)


async def main(paths: list[Path]) -> None:
    print(f"=== STT real-audio reproducer — STT_URL={STT_URL} ===", flush=True)
    for p in paths:
        if not p.exists():
            print(f"\nSKIP (missing): {p}", flush=True)
            continue
        await run_one(p)
    print("\nDone.", flush=True)


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("usage: python3 stt_real_audio_probe.py <wav> [<wav> ...]")
        sys.exit(2)
    asyncio.run(main([Path(p) for p in sys.argv[1:]]))
