from pathlib import Path
import asyncio
import json
import edge_tts
from text_processor import NarrationCue
import config

from checkpoint_manager import (
    cleanup_corrupted_chunk,
    save_chunk_atomically,
    validate_cached_chunk,
)

MAX_RETRIES = 3
RETRY_DELAY_SECONDS = 3
TICKS_PER_SECOND = 10_000_000

def cache_path_for(audio_path: Path) -> Path:
    return audio_path.with_suffix(".json")

async def synthesize_cue(cue: NarrationCue, output_path: Path) -> dict:
    meta_path = cache_path_for(output_path)
    cached = validate_cached_chunk(output_path, meta_path, cue.text, voice=config.VOICE)
    if cached is not None:
        return cached

    active_voice = config.VOICE
    rate = cue.rate or config.SPEECH_RATE
    pitch = cue.pitch or config.SPEECH_PITCH
    volume = cue.volume or config.SPEECH_VOLUME
    last_error = None
    for attempt in range(1, MAX_RETRIES + 1):
        try:
            communicate = edge_tts.Communicate(text=cue.text, voice=active_voice, rate=rate, volume=volume, pitch=pitch, boundary="WordBoundary",)
            audio_data = bytearray()
            boundaries = []

            async for message in communicate.stream():
                message_type = message.get("type")
                if message_type == "audio":
                    data = message.get("data")
                    if data:
                        audio_data.extend(data)

                elif message_type == "WordBoundary":
                    offset = message.get("offset", 0)
                    duration = message.get("duration", 0)
                    text = message.get("text", "")
                    boundaries.append({"offset_ms": (offset / TICKS_PER_SECOND * 1000), "duration_ms": (duration / TICKS_PER_SECOND * 1000), "text": text,})

            if not audio_data:
                raise RuntimeError("Edge TTS returned no audio.")

            metadata = {"text": cue.text, "voice": active_voice, "rate": rate, "pitch": pitch, "volume": volume, "boundaries": boundaries,}
            # Atomically write audio & metadata files
            save_chunk_atomically(output_path, bytes(audio_data), metadata)
            return metadata

        except Exception as error:
            last_error = error
            cleanup_corrupted_chunk(output_path, meta_path)
            if attempt < MAX_RETRIES:
                await asyncio.sleep(RETRY_DELAY_SECONDS)

    raise RuntimeError(f"TTS failed after {MAX_RETRIES} attempts: {last_error}")