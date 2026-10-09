from pathlib import Path
from config import (
    AUDIO_BITRATE,
    ENABLE_SUBTITLES,
    SUBTITLE_FORMAT,
)

# ------------------------------------------------------------
# Time formatting
# ------------------------------------------------------------

def format_srt_timestamp(milliseconds: int) -> str:
    total_seconds = milliseconds // 1000
    hours = total_seconds // 3600
    minutes = (total_seconds % 3600) // 60
    seconds = total_seconds % 60
    millis = milliseconds % 1000

    return (
        f"{hours:02d}:"
        f"{minutes:02d}:"
        f"{seconds:02d},"
        f"{millis:03d}"
    )

# ------------------------------------------------------------
# FFMetadata
# ------------------------------------------------------------

def check_ffmpeg():
    import shutil
    if shutil.which("ffmpeg") is None:
        raise RuntimeError("\nFFmpeg was not found on this system.\n\nInstall FFmpeg using Windows Package Manager (winget):\n\n    winget install -e --id Gyan.FFmpeg\n\nAfter installation, restart your terminal and run this program again.\n")

def create_ffmetadata(output_path: Path, title: str, author: str, chapters,):
    lines = [";FFMETADATA1", f"title={title}", f"artist={author}", f"album={title}", "",]
    for chapter in chapters:
        lines.extend(["[CHAPTER]", "TIMEBASE=1/1000", f"START={chapter['start']}", f"END={chapter['end']}", f"title={chapter['title']}", "",])

    output_path.write_text("\n".join(lines), encoding="utf-8",)

# ------------------------------------------------------------
# SRT generation
# ------------------------------------------------------------

def format_srt_timestamp(milliseconds: int) -> str:
    total_seconds = milliseconds // 1000
    hours = total_seconds // 3600
    minutes = (total_seconds % 3600) // 60
    seconds = total_seconds % 60
    millis = milliseconds % 1000
    return (f"{hours:02d}: {minutes:02d}: {seconds:02d}, {millis:03d}")

def create_srt(output_path: Path, subtitle_cues,):
    lines = []
    for index, cue in enumerate(subtitle_cues, start=1,):
        lines.append(str(index))
        lines.append(f"{format_srt_timestamp(cue['start'])} --> {format_srt_timestamp(cue['end'])}")
        lines.append(cue["text"])
        lines.append("")

    output_path.write_text("\n".join(lines), encoding="utf-8",)

# ------------------------------------------------------------
# Create M4B
# ------------------------------------------------------------

def create_m4b(combined_audio_path: Path, output_path: Path, metadata_path: Path, title: str, author: str, subtitle_path: Path | None = None,):
    import subprocess
    check_ffmpeg()
    command = ["ffmpeg", "-y", "-i", str(combined_audio_path), "-i", str(metadata_path),]
    if (ENABLE_SUBTITLES and subtitle_path is not None):
        command.extend(["-i", str(subtitle_path),])

    command.extend(["-map", "0:a", "-map_metadata", "1", "-map_chapters", "1", "-c:a", "aac", "-b:a", AUDIO_BITRATE,])
    if (ENABLE_SUBTITLES and subtitle_path is not None):
        command.extend(["-map", "2:0","-c:s", SUBTITLE_FORMAT,"-metadata:s:s:0", "language=eng","-metadata:s:s:0", "title=English",])

    command.extend(["-metadata", f"title={title}", "-metadata", f"artist={author}", "-metadata", f"album={title}", "-movflags", "+faststart", str(output_path),])
    subprocess.run(command, check=True,)