import asyncio
import os
import shutil
import tempfile
from pathlib import Path
import ui
from narrator import generate_section_audio
from pdf_processor import process_pdf
from text_processor import NarrationCue, split_text_for_tts
from tts_engine import synthesize_cue
from audiobook import (
    concat_audio_files,
    create_ffmetadata,
    create_mp4,
    create_srt,
    get_audio_duration_ms,
    safe_filename,
)
from config import (
    AUDIO_BITRATE,
    AUTO_OPEN_AUDIO,
    ENABLE_SUBTITLES,
    MAX_CONCURRENT_REQUESTS,
    MAX_SECTIONS,
    OUTPUT_DIRECTORY,
    OUTPUT_EXTENSION,
)
from image_processor import (
    build_slide_timeline,
    create_slides_manifest,
    extract_images_from_pdf,
)

async def run_audiobook_conversion():
    ui.show_banner()
    pdf_path = ui.select_pdf()
    if not pdf_path:
        ui.show_warning("No PDF selected.")
        return

    ui.show_selected_file(pdf_path.name)
    temp_directory = Path(tempfile.mkdtemp(prefix="audiobook_"))
    try:
        # --------------- Step 1: PDF Analysis & Visual Content Extraction ---------------
        ui.show_step_start(1, 5, "Analyzing PDF, detecting narrative sections & visual content...")
        try:
            title, author, sections = process_pdf(pdf_path)
            extracted_images = extract_images_from_pdf(pdf_path, temp_directory)

        except Exception as error:
            ui.show_error(f"Failed to process PDF: {error}")
            return

        if MAX_SECTIONS is not None:
            sections = sections[:MAX_SECTIONS]

        ui.show_book_metadata(title, author, len(sections), len(extracted_images))
        if not sections:
            ui.show_error("No narrative sections were found.")
            return

        ui.show_step_done(1, 5, "Analyzing PDF & detecting narrative sections")
        output_directory = Path(OUTPUT_DIRECTORY) if OUTPUT_DIRECTORY else pdf_path.parent
        output_directory.mkdir(parents=True, exist_ok=True)
        output_filename = f"{safe_filename(title)} ({safe_filename(author)}){OUTPUT_EXTENSION}"
        output_path = output_directory / output_filename

        # --------------- Step 2: Spoken Title/Author Introduction ---------------
        ui.show_step_start(2, 5, "Generating Introduction Audio...")
        intro_path = temp_directory / "introduction.mp3"
        intro_cue = NarrationCue(text=f"Title: {title}. Author: {author}.")
        try:
            await synthesize_cue(intro_cue, intro_path)
            intro_duration_ms = get_audio_duration_ms(intro_path)

        except Exception as error:
            raise RuntimeError(f"Unable to generate introduction: {error}") from error

        ui.show_step_done(2, 5, "Generating Introduction Audio")

        # --------------- Step 3: Parallel Narration Synthesis ---------------
        section_plan = []
        for section in sections:
            chunks = split_text_for_tts(section.text)
            if chunks:
                section_plan.append((section, chunks))

        total_steps = sum(len(chunks) + 1 for _, chunks in section_plan)
        ui.show_step_start(3, 5, f"Synthesizing Audiobook Narration ({MAX_CONCURRENT_REQUESTS} parallel workers)...")
        semaphore = asyncio.Semaphore(MAX_CONCURRENT_REQUESTS)
        section_files: list[Path] = []
        chapters: list[dict] = []
        subtitle_entries: list[dict] = []
        section_durations_ms: list[int] = []
        section_chunk_durations_ms: list[list[int]] = []
        current_position = intro_duration_ms
        with ui.NarrationProgress(total_steps=total_steps) as progress:
            for section_number, (section, chunks) in enumerate(section_plan, start=1):
                result = await generate_section_audio(section=section, section_number=section_number, temp_directory=temp_directory, chunks=chunks, semaphore=semaphore, on_progress=lambda c_idx, total_c, desc: progress.update_chunk( section_number, len(section_plan), section.title, desc),)
                if result is None:
                    continue

                section_files.append(result.audio_path)
                section_durations_ms.append(result.duration_ms)
                section_chunk_durations_ms.append(result.chunk_durations_ms)
                chapter_start = current_position
                chapter_end = current_position + result.duration_ms
                chapters.append({"start": chapter_start, "end": chapter_end, "title": section.title,})
                for cue in result.subtitle_cues:
                    subtitle_entries.append({"start": current_position + cue.start_ms, "end": current_position + cue.end_ms, "text": cue.text,})

                current_position = chapter_end

        ui.show_step_done(3, 5, "Synthesizing Audiobook Narration")

        # --------------- Step 4: Lossless Audio Combination, Subtitles & Slide Timeline ---------------
        ui.show_step_start(4, 5, "Combining Audio Tracks, Subtitles & Synchronizing Visual Slides...")
        combined_audio_path = temp_directory / "combined.mp3"
        concat_audio_files([intro_path] + section_files, combined_audio_path)
        metadata_path = temp_directory / "chapters.txt"
        create_ffmetadata(output_path=metadata_path, title=title, author=author, chapters=chapters)
        subtitle_path = None
        if ENABLE_SUBTITLES:
            subtitle_path = temp_directory / "subtitles.srt"
            create_srt(output_path=subtitle_path, subtitle_cues=subtitle_entries)

        slide_segments = build_slide_timeline(sections=[s for s, _ in section_plan], section_durations_ms=section_durations_ms, section_chunk_durations_ms=section_chunk_durations_ms, extracted_images=extracted_images, intro_duration_ms=intro_duration_ms, temp_directory=temp_directory,)
        slides_manifest_path = None
        if slide_segments:
            slides_manifest_path = temp_directory / "slides.txt"
            create_slides_manifest(slide_segments, slides_manifest_path)

        ui.show_step_done(4, 5, "Combining Audio Tracks & Synchronizing Visual Slides")

        # --------------- Step 5: Encoding Final MP4 ---------------
        ui.show_step_start(5, 5, f"Encoding Final MP4 ({AUDIO_BITRATE} Audio, Subtitles & Visual Slides)...")
        total_seconds = max(1, current_position // 1000)
        with ui.EncodingProgress(total_seconds=total_seconds) as enc_progress:
            try:
                create_mp4(combined_audio_path=combined_audio_path, output_path=output_path, metadata_path=metadata_path, title=title, author=author, slides_manifest_path=slides_manifest_path, subtitle_path=subtitle_path, total_duration_ms=current_position, on_progress=enc_progress.update_seconds,)

            except Exception as error:
                ui.show_error(f"Encoding failed: {error}")
                return

        ui.show_step_done(5, 5, "Encoding Final MP4")
        ui.show_completion(output_path=output_path, duration_minutes=current_position / 1000 / 60, bitrate=AUDIO_BITRATE, subtitles_enabled=ENABLE_SUBTITLES, slides_count=len(slide_segments),)
        if AUTO_OPEN_AUDIO:
            os.startfile(output_path)

    finally:
        shutil.rmtree(temp_directory, ignore_errors=True)

if __name__ == "__main__":
    asyncio.run(run_audiobook_conversion())