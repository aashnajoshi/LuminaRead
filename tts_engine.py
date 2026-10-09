from pathlib import Path
import asyncio
import json
import edge_tts
from text_processor import NarrationCue
from config import (
    SPEECH_PITCH,
    SPEECH_RATE,
    SPEECH_VOLUME,
    VOICE,
)

MAX_RETRIES = 3
RETRY_DELAY_SECONDS = 3
TICKS_PER_SECOND = 10_000_000

def cache_path_for(audio_path: Path) -> Path:
    return audio_path.with_suffix(".json")

def load_cached_result(audio_path: Path):
    metadata_path = cache_path_for(audio_path)
    if not audio_path.exists():
        return None

    if not metadata_path.exists():
        return None

    try:
        data = json.loads(metadata_path.read_text(encoding="utf-8"))
    
    except (OSError, json.JSONDecodeError):
        return None

    return data

async def synthesize_cue(cue: NarrationCue, output_path: Path,):
    cached = load_cached_result(output_path)
    if cached is not None:
        return cached

    rate = cue.rate or SPEECH_RATE
    pitch = cue.pitch or SPEECH_PITCH
    volume = cue.volume or SPEECH_VOLUME
    last_error = None
    for attempt in range(1, MAX_RETRIES + 1,):
        try:
            communicate = edge_tts.Communicate(
                text=cue.text,
                voice=VOICE,
                rate=rate,
                volume=volume,
                pitch=pitch,
                boundary="SentenceBoundary",)
            audio_data = bytearray()
            boundaries = []
            async for message in communicate.stream():
                message_type = message.get("type")
                if message_type == "audio":
                    data = message.get("data")
                    if data:
                        audio_data.extend(data)

                elif (message_type == "SentenceBoundary"):
                    offset = message.get("offset", 0,)
                    duration = message.get("duration", 0,)
                    text = message.get("text", "",)
                    boundaries.append({
                        "offset_ms": (offset / TICKS_PER_SECOND * 1000),
                        "duration_ms": (duration / TICKS_PER_SECOND * 1000),
                        "text": text,
                    })

            if not audio_data:
                raise RuntimeError("Edge TTS returned no audio.")

            output_path.write_bytes(bytes(audio_data))
            metadata = {
                "text": cue.text,
                "voice": VOICE,
                "rate": rate,
                "pitch": pitch,
                "volume": volume,
                "boundaries": boundaries,
            }

            metadata_path = cache_path_for(output_path)
            metadata_path.write_text(
                json.dumps(
                    metadata,
                    ensure_ascii=False,
                    indent=2,
                ),
                encoding="utf-8",
            )

            return metadata

        except Exception as error:
            last_error = error
            try:
                output_path.unlink(missing_ok=True)
            
            except OSError:
                pass

            try:
                cache_path_for(output_path).unlink(missing_ok=True)
            
            except OSError:
                pass

            if attempt < MAX_RETRIES:
                await asyncio.sleep(RETRY_DELAY_SECONDS)

    raise RuntimeError(f"TTS failed after {MAX_RETRIES} attempts: {last_error}")