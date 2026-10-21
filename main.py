import asyncio
import os
from pathlib import Path
import shutil
from cli import apply_cli_overrides, parse_cli_args
import config
from narrator import generate_section_audio
from pdf_processor import process_pdf
from text_processor import NarrationCue, split_text_for_tts
from tts_engine import synthesize_cue
import ui

from audiobook import (
    concat_audio_files,
    create_ffmetadata,
    create_mp4,
    create_srt,
    get_audio_duration_ms,
    safe_filename,
)
from checkpoint_manager import (
    cleanup_intermediate_chunks,
    count_resumed_progress,
    get_checkpoint_dir,
    load_extracted_images_cache,
    save_extracted_images_cache,
)
from image_processor import (
    build_slide_timeline,
    create_slides_manifest,
    extract_images_from_pdf,
)

async def run_audiobook_conversion():
    parsed_args = parse_cli_args()
    apply_cli_overrides(parsed_args)
    ui.show_banner()
    pdf_path = ui.select_pdf(parsed_args.pdf)
    if not pdf_path:
        ui.show_warning("No PDF selected.")
        return

    ui.show_selected_file(pdf_path.name)
    output_directory = Path(config.OUTPUT_DIRECTORY) if config.OUTPUT_DIRECTORY else pdf_path.parent
    output_directory.mkdir(parents=True, exist_ok=True)
    session_directory = get_checkpoint_dir(pdf_path, output_directory)
    if parsed_args.force_restart and session_directory.exists():
        shutil.rmtree(session_directory, ignore_errors=True)
        session_directory.mkdir(parents=True, exist_ok=True)

    conversion_succeeded = False
    try:
        # --------------- Step 1: PDF Analysis & Visual Content Extraction ---------------
        ui.show_step_start(1, 5, "Analyzing PDF, detecting narrative sections & visual content...")
        ocr_pbar = None

        def on_scanned_detected(total_pages: int, reason: str):
            nonlocal ocr_pbar
            ui.show_ocr_fallback(total_pages, reason)
            ocr_pbar = ui.OCRProgress(total_pages=total_pages)
            ocr_pbar.__enter__()

        def on_ocr_progress(page_idx: int, total_pages: int):
            if ocr_pbar:
                ocr_pbar.update_page(page_idx)

        try:
            try:
                title, author, sections = process_pdf(pdf_path=pdf_path, force_ocr=parsed_args.force_ocr, session_directory=session_directory, on_scanned_detected=on_scanned_detected, on_ocr_progress=on_ocr_progress,)

            finally:
                if ocr_pbar:
                    ocr_pbar.__exit__(None, None, None)

            extracted_images = load_extracted_images_cache(session_directory)
            if extracted_images is None:
                extracted_images = extract_images_from_pdf(pdf_path, session_directory)
                save_extracted_images_cache(session_directory, extracted_images)

        except Exception as error:
            ui.show_error(f"Failed to process PDF: {error}")
            return

        if config.MAX_SECTIONS is not None:
            sections = sections[:config.MAX_SECTIONS]

        ui.show_book_metadata(title, author, len(sections), len(extracted_images))
        if not sections:
            ui.show_error("No narrative sections were found.")
            return

        ui.show_step_done(1, 5, "Analyzing PDF & detecting narrative sections")
        output_filename = f"{safe_filename(title)} ({safe_filename(author)}){config.OUTPUT_EXTENSION}"
        output_path = output_directory / output_filename

        # --------------- Step 2: Spoken Title/Author Introduction ---------------
        ui.show_step_start(2, 5, "Generating Introduction Audio...")
        intro_path = session_directory / "introduction.mp3"
        intro_cue = NarrationCue(text=f"Title: {title}. Author: {author}.")
        try:
            await synthesize_cue(intro_cue, intro_path)
            intro_duration_ms = get_audio_duration_ms(intro_path)

        except Exception as error:
            raise RuntimeError(f"Unable to generate introduction: {error}") from error

        ui.show_step_done(2, 5, "Generating Introduction Audio")

        # --------------- Step 3: Parallel Narration Synthesis with Checkpoint Resume ---------------
        section_plan = []
        for section in sections:
            chunks = split_text_for_tts(section.text)
            if chunks:
                section_plan.append((section, chunks))

        total_steps = sum(len(chunks) + 1 for _, chunks in section_plan)
        cached_sections, cached_steps, _ = count_resumed_progress(session_directory, section_plan)
        if cached_steps > 0:
            ui.show_checkpoint_found(cached_sections, len(section_plan), cached_steps, total_steps)

        ui.show_step_start(3, 5, f"Synthesizing Audiobook Narration ({config.MAX_CONCURRENT_REQUESTS} parallel workers)...")
        semaphore = asyncio.Semaphore(config.MAX_CONCURRENT_REQUESTS)
        section_files: list[Path] = []
        chapters: list[dict] = []
        subtitle_entries: list[dict] = []
        section_durations_ms: list[int] = []
        section_chunk_durations_ms: list[list[int]] = []
        current_position = intro_duration_ms
        with ui.NarrationProgress(total_steps=total_steps, initial_steps=0) as progress:
            for section_number, (section, chunks) in enumerate(section_plan, start=1):
                result = await generate_section_audio(section=section, section_number=section_number, temp_directory=session_directory, chunks=chunks, semaphore=semaphore, on_progress=lambda c_idx, total_c, desc: progress.update_chunk(section_number, len(section_plan), section.title, desc),)
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
        combined_audio_path = session_directory / "combined.mp3"
        concat_audio_files([intro_path] + section_files, combined_audio_path)
        metadata_path = session_directory / "chapters.txt"
        create_ffmetadata(output_path=metadata_path, title=title, author=author, chapters=chapters)
        subtitle_path = None
        if config.ENABLE_SUBTITLES:
            subtitle_path = session_directory / "subtitles.srt"
            create_srt(output_path=subtitle_path, subtitle_cues=subtitle_entries)

        slide_segments = build_slide_timeline(sections=[s for s, _ in section_plan], section_durations_ms=section_durations_ms, section_chunk_durations_ms=section_chunk_durations_ms, extracted_images=extracted_images, intro_duration_ms=intro_duration_ms, temp_directory=session_directory,)
        slides_manifest_path = None
        if slide_segments:
            slides_manifest_path = session_directory / "slides.txt"
            create_slides_manifest(slide_segments, slides_manifest_path)

        ui.show_step_done(4, 5, "Combining Audio Tracks & Synchronizing Visual Slides")

        # --------------- Step 5: Encoding Final MP4 ---------------
        ui.show_step_start(5, 5, f"Encoding Final MP4 ({config.AUDIO_BITRATE} Audio, Subtitles & Visual Slides)...")
        total_seconds = max(1, current_position // 1000)
        with ui.EncodingProgress(total_seconds=total_seconds) as enc_progress:
            try:
                create_mp4(combined_audio_path=combined_audio_path, output_path=output_path, metadata_path=metadata_path, title=title, author=author, slides_manifest_path=slides_manifest_path, subtitle_path=subtitle_path, total_duration_ms=current_position, on_progress=enc_progress.update_seconds,)

            except Exception as error:
                ui.show_error(f"Encoding failed: {error}")
                return

        ui.show_step_done(5, 5, "Encoding Final MP4")
        conversion_succeeded = True
        ui.show_completion(output_path=output_path, duration_minutes=current_position / 1000 / 60, bitrate=config.AUDIO_BITRATE, subtitles_enabled=config.ENABLE_SUBTITLES, slides_count=len(slide_segments),)
        if config.AUTO_OPEN_AUDIO:
            os.startfile(output_path)

    finally:
        if conversion_succeeded:
            cleanup_intermediate_chunks(session_directory, len(sections))
            if not config.ENABLE_CHECKPOINTS:
                shutil.rmtree(session_directory, ignore_errors=True)

        else:
            if not config.ENABLE_CHECKPOINTS:
                shutil.rmtree(session_directory, ignore_errors=True)

if __name__ == "__main__":
    asyncio.run(run_audiobook_conversion())