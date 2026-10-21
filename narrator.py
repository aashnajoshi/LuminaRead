import asyncio
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path
from config import KEEP_TTS_SEGMENTS, MAX_CONCURRENT_REQUESTS
from pdf_processor import Section
from tts_engine import cache_path_for, synthesize_cue
from audiobook import concat_audio_files, get_audio_duration_ms, get_or_create_silence

from checkpoint_manager import (
    save_section_checkpoint,
    validate_cached_chunk,
    validate_section_checkpoint,
)
from text_processor import (
    SubtitleCue,
    create_heading_cue,
    group_words_into_subtitle_cues,
    interpret_text,
    split_text_for_tts,
)

@dataclass
class SectionAudioResult:
    audio_path: Path
    duration_ms: int
    subtitle_cues: list[SubtitleCue]
    chunk_durations_ms: list[int] = field(default_factory=list)

async def generate_section_audio(section: Section, section_number: int, temp_directory: Path, chunks: list[str] | None = None, semaphore: asyncio.Semaphore | None = None, on_progress: Callable[[int, int, str], None] | None = None,) -> SectionAudioResult | None:
    if chunks is None:
        chunks = split_text_for_tts(section.text)

    if not chunks:
        return None

    if semaphore is None:
        semaphore = asyncio.Semaphore(MAX_CONCURRENT_REQUESTS)

    section_dir = temp_directory / f"section_{section_number:03d}"
    section_dir.mkdir(parents=True, exist_ok=True)

    # 1. Check if the entire section was already completed & checkpointed
    cached_section = validate_section_checkpoint(section_dir, section_number, len(chunks))
    if cached_section is not None:
        if on_progress:
            on_progress(0, len(chunks), "Heading (Cached)")
            for i in range(1, len(chunks) + 1):
                on_progress(i, len(chunks), f"Chunk {i}/{len(chunks)} (Cached)")

        return cached_section

    # 2. Synthesize Heading (cached if already valid)
    heading_cue = create_heading_cue(section.title)
    heading_path = section_dir / "heading.mp3"
    await synthesize_cue(heading_cue, heading_path)
    if on_progress:
        on_progress(0, len(chunks), "Heading")

    # 3. Synthesize all chunks concurrently (reusing any valid cached chunks)
    chunk_results: list[dict | None] = [None] * len(chunks)
    temporary_files = [heading_path]

    async def synthesize_worker(index: int, text: str):
        chunk_path = section_dir / f"chunk_{index:04d}.mp3"
        meta_path = cache_path_for(chunk_path)
        cached_meta = validate_cached_chunk(chunk_path, meta_path, text)
        if cached_meta is not None:
            cue = interpret_text(text)
            chunk_results[index - 1] = {"cue": cue, "path": chunk_path, "metadata": cached_meta, "text": text,}
            if on_progress:
                on_progress(index, len(chunks), f"Chunk {index}/{len(chunks)} (Cached)")

            return

        async with semaphore:
            cue = interpret_text(text)
            metadata = await synthesize_cue(cue, chunk_path)
            chunk_results[index - 1] = {"cue": cue, "path": chunk_path, "metadata": metadata, "text": text,}
            if on_progress:
                on_progress(index, len(chunks), f"Chunk {index}/{len(chunks)}")

    tasks = [synthesize_worker(i, c) for i, c in enumerate(chunks, start=1)]
    await asyncio.gather(*tasks)

    # 4. Assemble audio segments & subtitle cues in strict chronological order
    ordered_audio_files: list[Path] = []
    subtitle_cues: list[SubtitleCue] = []
    chunk_durations_ms: list[int] = []
    current_time_ms = 0
    heading_dur = get_audio_duration_ms(heading_path)
    ordered_audio_files.append(heading_path)
    subtitle_cues.append(SubtitleCue(start_ms=current_time_ms, end_ms=current_time_ms + heading_dur, text=section.title,))
    current_time_ms += heading_dur
    if heading_cue.pause_after_ms:
        silence = get_or_create_silence(temp_directory, heading_cue.pause_after_ms)
        ordered_audio_files.append(silence)
        current_time_ms += heading_cue.pause_after_ms

    for item in chunk_results:
        if item is None:
            continue

        cue = item["cue"]
        chunk_path = item["path"]
        metadata = item["metadata"]
        text = item["text"]
        temporary_files.append(chunk_path)
        chunk_start_before_pause = current_time_ms
        if cue.pause_before_ms:
            silence = get_or_create_silence(temp_directory, cue.pause_before_ms)
            ordered_audio_files.append(silence)
            current_time_ms += cue.pause_before_ms

        chunk_dur = get_audio_duration_ms(chunk_path)
        word_boundaries = metadata.get("boundaries", [])
        if word_boundaries:
            grouped_cues = group_words_into_subtitle_cues(original_text=text, word_events=word_boundaries,)
            for cue_item in grouped_cues:
                subtitle_cues.append(SubtitleCue(start_ms=current_time_ms + cue_item.start_ms, end_ms=current_time_ms + cue_item.end_ms, text=cue_item.text,))

        ordered_audio_files.append(chunk_path)
        current_time_ms += chunk_dur
        if cue.pause_after_ms:
            silence = get_or_create_silence(temp_directory, cue.pause_after_ms)
            ordered_audio_files.append(silence)
            current_time_ms += cue.pause_after_ms

        chunk_durations_ms.append(current_time_ms - chunk_start_before_pause)

    # 5. Fast lossless concatenation using FFmpeg
    section_path = section_dir / f"section_{section_number:03d}.mp3"
    concat_audio_files(ordered_audio_files, section_path)
    result = SectionAudioResult(audio_path=section_path, duration_ms=current_time_ms, subtitle_cues=subtitle_cues, chunk_durations_ms=chunk_durations_ms,)

    # 6. Save section-level checkpoint
    save_section_checkpoint(section_dir, section_number, result)

    # 7. Cleanup individual chunk audio files if configured
    if not KEEP_TTS_SEGMENTS:
        for file_path in temporary_files:
            try:
                file_path.unlink(missing_ok=True)

            except OSError:
                pass

            metadata_path = file_path.with_suffix(".json")
            try:
                metadata_path.unlink(missing_ok=True)

            except OSError:
                pass

    return result