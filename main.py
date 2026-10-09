import asyncio
import os
import shutil
import tempfile
from pathlib import Path
from tkinter import Tk, filedialog
from pydub import AudioSegment
from tqdm import tqdm
from narrator import generate_section_audio
from pdf_processor import process_pdf
from text_processor import NarrationCue
from tts_engine import synthesize_cue

from audiobook import (
    create_ffmetadata,
    create_m4b,
    create_srt,
)

from config import (
    AUTO_OPEN_AUDIO,
    ENABLE_SUBTITLES,
    MAX_SECTIONS,
    OUTPUT_DIRECTORY,
    OUTPUT_EXTENSION,
)

def select_pdf():
    root = Tk()
    root.withdraw()
    file_path = filedialog.askopenfilename(title="Select the PDF", filetypes=[("PDF files", "*.pdf"),],)
    root.destroy()
    if not file_path:
        return None

    return Path(file_path)

def safe_filename(name: str) -> str:
    invalid = '<>:"/\\|?*'
    for character in invalid:
        name = name.replace(character, "_",)

    return name.strip()

async def main():
    print()
    print("=" * 60)
    print("PDF TO AUDIOBOOK CONVERTER")
    print("=" * 60)
    print()
    pdf_path = select_pdf()
    if not pdf_path:
        print("No PDF selected.")
        return

    print(f"Selected PDF: {pdf_path.name}")
    print()
    print("Processing PDF...")
    
    try:
        title, author, sections = process_pdf(pdf_path)
    
    except Exception as error:
        print()
        print(f"ERROR: {error}")
        return

    if MAX_SECTIONS is not None:
        sections = sections[:MAX_SECTIONS]

    print(f"Title: {title}")
    print(f"Author: {author}")
    print(f"Sections: {len(sections)}")
    if not sections:
        print()
        print("ERROR: No narrative sections were found.")
        return

    if OUTPUT_DIRECTORY:
        output_directory = Path(OUTPUT_DIRECTORY)

    else:
        output_directory = pdf_path.parent

    output_directory.mkdir(parents=True, exist_ok=True,)
    output_name = (f"{safe_filename(title)} ({safe_filename(author)}){OUTPUT_EXTENSION}")
    output_path = (output_directory / output_name)
    temp_directory = Path(tempfile.mkdtemp(prefix="audiobook_"))
    try:
        print()
        print("Generating introduction...")
        intro_path = (temp_directory/ "introduction.mp3")
        intro_cue = NarrationCue(text=(f"Title: {title}. Author: {author}."))
        try:
            await synthesize_cue(intro_cue, intro_path,)
        
        except Exception as error:
            raise RuntimeError(f"Unable to generate introduction: {error}") from error

        intro_audio = AudioSegment.from_file(intro_path, format="mp3",)
        section_files = []
        chapters = []
        subtitle_entries = []
        current_position = len(intro_audio)
        print()
        print("Generating audiobook audio...")
        progress = tqdm(sections, desc="Sections", unit="section", dynamic_ncols=True,)
        for section_number, section in enumerate(progress, start=1,):
            progress.set_postfix_str(section.title[:35])
            try:
                result = await generate_section_audio(section=section, section_number=section_number, temp_directory=temp_directory,)
            
            except Exception as error:
                raise RuntimeError(f"Failed while generating '{section.title}': {error}") from error

            if result is None:
                continue

            section_files.append(result.audio_path)
            chapter_start = (current_position)
            chapter_end = (current_position + result.duration_ms)
            chapters.append({
                "start": chapter_start,
                "end": chapter_end,
                "title": section.title,
            })
            for cue in result.subtitle_cues:
                subtitle_entries.append({
                    "start": (current_position + cue.start_ms),
                    "end": (current_position + cue.end_ms),
                    "text": cue.text,
                })

            current_position = chapter_end

        progress.close()
        print()
        print("Combining audio...")
        combined_audio = intro_audio
        for section_path in section_files:
            audio = AudioSegment.from_file(section_path, format="mp3",)
            combined_audio += audio

        combined_audio_path = (temp_directory / "combined.mp3")
        combined_audio.export(combined_audio_path, format="mp3", bitrate="192k",)
        metadata_path = (temp_directory / "chapters.txt")
        create_ffmetadata(output_path=metadata_path, title=title, author=author, chapters=chapters,)
        subtitle_path = None
        if ENABLE_SUBTITLES:
            print("Preparing subtitle track...")
            subtitle_path = (temp_directory / "subtitles.srt")
            create_srt(output_path=subtitle_path, subtitle_cues=subtitle_entries,)

        print("Creating final M4B...")
        try:
            create_m4b(
                combined_audio_path=combined_audio_path,
                output_path=output_path,
                metadata_path=metadata_path,
                title=title,
                author=author,
                subtitle_path=subtitle_path,
            )
        
        except Exception as error:
            print()
            print(f"ERROR: {error}")
            return

        print()
        print("=" * 60)
        print("AUDIOBOOK COMPLETE")
        print("=" * 60)
        print()
        print(f"Output: {output_path}")
        duration_minutes = (len(combined_audio) / 1000 / 60)
        print(f"Duration: {duration_minutes:.1f} minutes")
        if ENABLE_SUBTITLES:
            print("Subtitles: Enabled")
        
        else: print("Subtitles: Disabled")

        print()
        if AUTO_OPEN_AUDIO:
            os.startfile(output_path)

    finally:
        shutil.rmtree(temp_directory, ignore_errors=True,)

if __name__ == "__main__":
    try:
        asyncio.run(main())
    
    except KeyboardInterrupt:
        print("\n\nCancelled by user.")