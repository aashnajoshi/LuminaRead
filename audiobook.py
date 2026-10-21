from collections.abc import Callable
from pathlib import Path
import re
import shutil
import subprocess
import config

# --------------- System Checks & Helpers ---------------
def check_ffmpeg():
    if shutil.which("ffmpeg") is None:
        raise RuntimeError("\nFFmpeg was not found on this system.\n\nInstall FFmpeg using Windows Package Manager (winget):\n\n    winget install -e --id Gyan.FFmpeg\n\nAfter installation, restart your terminal and run this program again.\n")

def safe_filename(name: str) -> str:
    invalid = '<>:"/\\|?*'
    for character in invalid:
        name = name.replace(character, "_")

    return name.strip()

def get_audio_duration_ms(file_path: Path) -> int:
    check_ffmpeg()
    command = [
        "ffprobe", "-v", "error",
        "-show_entries", "format=duration",
        "-of", "default=noprint_wrappers=1:nokey=1",
        str(file_path),
    ]
    res = subprocess.run(command, capture_output=True, text=True, check=True)
    return round(float(res.stdout.strip()) * 1000)

def get_or_create_silence(temp_dir: Path, duration_ms: int = 600) -> Path:
    silence_path = temp_dir / f"silence_{duration_ms}ms.mp3"
    if silence_path.exists():
        return silence_path

    sec = duration_ms / 1000.0
    command = [
        "ffmpeg", "-y", "-nostats", "-loglevel", "error",
        "-f", "lavfi", "-i", "anullsrc=r=24000:cl=mono",
        "-t", str(sec),
        "-c:a", "libmp3lame", "-b:a", "48k",
        str(silence_path),
    ]
    try:
        subprocess.run(command, check=True, capture_output=True)

    except subprocess.CalledProcessError as err:
        raise RuntimeError(f"Silence generation failed: {err.stderr.decode('utf-8', errors='ignore')}") from err

    return silence_path

def concat_audio_files(file_list: list[Path], output_path: Path):
    if not file_list:
        return

    check_ffmpeg()
    list_file = output_path.with_suffix(".txt")
    lines = [f"file '{f.as_posix()}'" for f in file_list]
    list_file.write_text("\n".join(lines), encoding="utf-8")
    command = [
        "ffmpeg", "-y", "-nostats", "-loglevel", "error",
        "-fflags", "+genpts",
        "-f", "concat", "-safe", "0",
        "-i", str(list_file),
        "-c", "copy",
        str(output_path),
    ]
    try:
        subprocess.run(command, check=True, capture_output=True)

    except subprocess.CalledProcessError as err:
        raise RuntimeError(f"Audio concatenation failed: {err.stderr.decode('utf-8', errors='ignore')}") from err

    finally:
        list_file.unlink(missing_ok=True)

# --------------- FFMetadata ---------------
def create_ffmetadata(output_path: Path, title: str, author: str, chapters: list[dict]):
    lines = [";FFMETADATA1", f"title={title}", f"artist={author}", f"album={title}", ""]
    for chapter in chapters:
        lines.extend([
            "[CHAPTER]",
            "TIMEBASE=1/1000",
            f"START={chapter['start']}",
            f"END={chapter['end']}",
            f"title={chapter['title']}",
            "",
        ])
    output_path.write_text("\n".join(lines), encoding="utf-8")

# --------------- SRT Generation ---------------
def format_srt_timestamp(milliseconds: int) -> str:
    total_seconds = milliseconds // 1000
    hours = total_seconds // 3600
    minutes = (total_seconds % 3600) // 60
    seconds = total_seconds % 60
    millis = milliseconds % 1000
    return f"{hours:02d}:{minutes:02d}:{seconds:02d},{millis:03d}"

def create_srt(output_path: Path, subtitle_cues):
    lines = []
    for index, cue in enumerate(subtitle_cues, start=1):
        start_ms = cue["start"] if isinstance(cue, dict) else cue.start_ms
        end_ms = cue["end"] if isinstance(cue, dict) else cue.end_ms
        text = cue["text"] if isinstance(cue, dict) else cue.text
        lines.append(str(index))
        lines.append(f"{format_srt_timestamp(start_ms)} --> {format_srt_timestamp(end_ms)}")
        lines.append(text)
        lines.append("")

    output_path.write_text("\n".join(lines), encoding="utf-8")

# ------------------------------------------------------------
# Create MP4 (Audiobook with Black Canvas, Chapters, & Soft Subtitles)
# ------------------------------------------------------------

def create_mp4(combined_audio_path: Path, output_path: Path, metadata_path: Path, title: str, author: str, slides_manifest_path: Path | None = None, subtitle_path: Path | None = None, total_duration_ms: int | None = None, on_progress: Callable[[float], None] | None = None,):
    check_ffmpeg()
    command = [
        "ffmpeg", "-y",
        "-nostats", "-loglevel", "error",
        "-progress", "pipe:1",
    ]
    if slides_manifest_path is not None and slides_manifest_path.exists():
        command.extend(["-f", "concat", "-safe", "0", "-i", str(slides_manifest_path)])

    else:
        command.extend(["-f", "lavfi", "-i", "color=c=black:s=1280x720:r=1"])

    command.extend([
        "-i", str(combined_audio_path),
        "-i", str(metadata_path),
    ])
    if config.ENABLE_SUBTITLES and subtitle_path is not None:
        command.extend(["-i", str(subtitle_path)])

    command.extend([
        "-map", "0:v",
        "-map", "1:a",
        "-map_metadata", "2",
        "-map_chapters", "2",
        "-c:v", "libx264",
        "-tune", "stillimage",
        "-pix_fmt", "yuv420p",
        "-crf", "35",
        "-r", "1",
        "-c:a", "aac",
        "-b:a", config.AUDIO_BITRATE,
    ])
    if config.ENABLE_SUBTITLES and subtitle_path is not None:
        command.extend([
            "-map", "3:0",
            "-c:s", config.SUBTITLE_FORMAT,
            "-metadata:s:s:0", "language=eng",
            "-metadata:s:s:0", "title=English",
        ])
        if config.SUBTITLES_DEFAULT_ON:
            command.extend(["-disposition:s:0", "default+forced"])

        else:
            command.extend(["-disposition:s:0", "0"])

    command.extend([
        "-metadata", f"title={title}",
        "-metadata", f"artist={author}",
        "-metadata", f"album={title}",
        "-metadata", "genre=Audiobook",
        "-metadata", "media_type=2",
        "-metadata", "show_movement=1",
        "-metadata", "gapless_playback=1",
    ])
    if total_duration_ms is not None and total_duration_ms > 0:
        duration_sec = total_duration_ms / 1000.0
        command.extend(["-t", f"{duration_sec:.3f}"])

    else:
        command.extend(["-shortest"])

    command.extend(["-movflags", "+faststart", str(output_path)])
    process = subprocess.Popen(command, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
    time_regex = re.compile(r"out_time_us=(\d+)")
    last_seconds = 0.0
    error_lines = []
    try:
        if process.stdout:
            for line in process.stdout:
                match = time_regex.search(line)
                if match:
                    current_s = int(match.group(1)) / 1_000_000.0
                    diff = current_s - last_seconds
                    if diff > 0:
                        if on_progress:
                            on_progress(diff)

                        last_seconds = current_s

                else:
                    lower = line.lower()
                    if "error" in lower or "fatal" in lower:
                        error_lines.append(line.strip())

        process.wait()
        if process.returncode != 0:
            err_msg = "\n".join(error_lines) or f"Process exited with code {process.returncode}"
            raise RuntimeError(f"FFmpeg encoding failed: {err_msg}")

    finally:
        pass

create_m4b = create_mp4