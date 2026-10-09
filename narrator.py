from dataclasses import dataclass
from pathlib import Path
from pydub import AudioSegment
from config import KEEP_TTS_SEGMENTS
from pdf_processor import Section
from tts_engine import synthesize_cue

from text_processor import (
    create_heading_cue,
    interpret_text,
    split_text_for_tts,
)

@dataclass
class SubtitleCue:
    start_ms: int
    end_ms: int
    text: str

@dataclass
class SectionAudioResult:
    audio_path: Path
    duration_ms: int
    subtitle_cues: list[SubtitleCue]

async def generate_section_audio(section: Section, section_number: int, temp_directory: Path,) -> SectionAudioResult | None:
    chunks = split_text_for_tts(section.text)
    if not chunks:
        return None

    combined_audio = AudioSegment.empty()
    temporary_files = []
    subtitle_cues = []
    heading_cue = create_heading_cue(section.title)
    heading_path = (temp_directory / (f"section_{section_number:03d}_heading.mp3"))

    await synthesize_cue(heading_cue, heading_path,)
    heading_audio = AudioSegment.from_file(heading_path, format="mp3",)
    heading_start = len(combined_audio)
    combined_audio += heading_audio
    heading_end = len(combined_audio)
    subtitle_cues.append(
        SubtitleCue(
            start_ms=heading_start,
            end_ms=heading_end,
            text=section.title,
        )
    )

    temporary_files.append(heading_path)
    if heading_cue.pause_after_ms:
        combined_audio += (AudioSegment.silent(duration=heading_cue.pause_after_ms))

    for chunk_index, chunk in enumerate(chunks, start=1,):
        cue = interpret_text(chunk)
        chunk_path = (temp_directory / (f"section_{section_number:03d}_chunk_{chunk_index:04d}.mp3"))
        metadata = await synthesize_cue(cue, chunk_path,)
        audio = AudioSegment.from_file(chunk_path, format="mp3",)
        if cue.pause_before_ms:
            combined_audio += (AudioSegment.silent(duration=cue.pause_before_ms))

        chunk_start = len(combined_audio)
        combined_audio += audio
        for boundary in metadata.get("boundaries", [],):
            start_ms = (chunk_start + round(boundary["offset_ms"]))
            end_ms = (start_ms + round(boundary["duration_ms"]))
            text = boundary["text"].strip()
            if not text:
                continue

            subtitle_cues.append(
                SubtitleCue(
                    start_ms=start_ms,
                    end_ms=end_ms,
                    text=text,
                ))

        if cue.pause_after_ms:
            combined_audio += (AudioSegment.silent(duration=cue.pause_after_ms))

        temporary_files.append(chunk_path)

    section_path = (temp_directory / f"section_{section_number:03d}.mp3")
    combined_audio.export(section_path, format="mp3", bitrate="192k",)
    if not KEEP_TTS_SEGMENTS:
        for file_path in temporary_files:
            try:
                file_path.unlink(missing_ok=True)

            except OSError:
                pass

            metadata_path = (file_path.with_suffix(".json"))
            try:
                metadata_path.unlink(missing_ok=True)

            except OSError:
                pass

    return SectionAudioResult(audio_path=section_path, duration_ms=len(combined_audio), subtitle_cues=subtitle_cues,)