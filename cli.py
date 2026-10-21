import argparse
from pathlib import Path
import config

def normalize_speed(speed_val: str | None) -> str:
    """Normalizes speech rate inputs like '+10%', '-5%', '15%', or float multipliers like '1.2' into Edge TTS rate format."""
    if not speed_val:
        return config.SPEECH_RATE

    s = speed_val.strip()
    if s.endswith("%"):
        if not s.startswith(("+", "-")):
            return f"+{s}"

        return s

    try:
        val = float(s)
        pct = int(round((val - 1.0) * 100))
        sign = "+" if pct >= 0 else ""
        return f"{sign}{pct}%"

    except ValueError:
        return s

def get_cli_parser() -> argparse.ArgumentParser:
    """Constructs the command-line argument parser for LuminaRead."""
    parser = argparse.ArgumentParser(
        prog="python main.py",
        description="LuminaRead - Converts PDF documents, books, and reports into high-fidelity MP4 audiobooks with synchronized visual slides and dialogue subtitles.",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,)
    parser.add_argument("pdf", nargs="?",
        type=str,
        default=None,
        help="Path to the PDF file. If omitted, opens the graphical file picker.",)
    parser.add_argument("-v", "--voice",
        type=str,
        default=config.VOICE,
        help="Neural TTS voice model (e.g. 'en-US-BrianNeural', 'en-US-AvaNeural', 'en-US-AndrewNeural', 'en-US-EmmaNeural').",)
    parser.add_argument("-s", "--speed",
        type=str,
        default=config.SPEECH_RATE,
        help="Narration speed adjustment (e.g. '+10%%', '-5%%', '1.25' for 1.25x).",)
    parser.add_argument("-o", "--output",
        type=str,
        default=None,
        help="Directory to save the final MP4 audiobook. Defaults to the same folder as the input PDF.",)
    parser.add_argument("-n", "--sections",
        type=int,
        default=None,
        help="Limit the maximum number of narrative sections to convert (useful for testing quick samples).",)
    parser.add_argument("-w", "--workers",
        type=int,
        default=config.MAX_CONCURRENT_REQUESTS,
        help="Number of concurrent TTS synthesis workers (recommended: 3 to 5).",)
    parser.add_argument("--ocr", "--force-ocr",
        dest="force_ocr",
        action="store_true",
        help="Force full-page OCR text recognition across all pages using RapidOCR (even if digital text is present).",)
    parser.add_argument("--no-images",
        action="store_true",
        help="Disable diagram and image extraction (narrate with clean visual canvas).",)
    parser.add_argument("--no-subtitles",
        action="store_true",
        help="Disable timed subtitle generation and embedding in the final MP4.",)
    parser.add_argument("--no-cache", "--force-restart",
        dest="force_restart",
        action="store_true",
        help="Disregard existing checkpoints and synthesize from scratch.",)
    parser.add_argument("-b", "--bitrate",
        type=str,
        default=config.AUDIO_BITRATE,
        help="Audio bitrate for final MP4 audio stream (e.g. '192k', '320k').",)
    parser.add_argument("--open",
        action="store_true",
        help="Automatically launch the finished MP4 audiobook in your default media player upon completion.",)
    parser.add_argument("--no-layout", "--disable-multicolumn",
        dest="disable_multicolumn",
        action="store_true",
        help="Disable multi-column layout analysis and extract text strictly top-to-bottom.",)
    parser.add_argument("--keep-citations",
        action="store_true",
        help="Keep raw academic citations (e.g. '[1, 2]', '(Smith, 2020)') and URLs instead of cleaning them for speech.",)
    return parser

def parse_cli_args(args: list[str] | None = None) -> argparse.Namespace:
    """Parses command-line arguments passed to LuminaRead."""
    parser = get_cli_parser()
    return parser.parse_args(args)

def apply_cli_overrides(parsed_args: argparse.Namespace) -> None:
    """Applies parsed command-line arguments to global config parameters."""
    if parsed_args.voice:
        config.VOICE = parsed_args.voice

    if parsed_args.speed:
        config.SPEECH_RATE = normalize_speed(parsed_args.speed)

    if parsed_args.output:
        config.OUTPUT_DIRECTORY = parsed_args.output

    if parsed_args.sections is not None:
        config.MAX_SECTIONS = parsed_args.sections

    if parsed_args.workers is not None:
        config.MAX_CONCURRENT_REQUESTS = parsed_args.workers

    if parsed_args.no_images:
        config.ENABLE_IMAGE_EXTRACTION = False

    if parsed_args.no_subtitles:
        config.ENABLE_SUBTITLES = False

    if parsed_args.bitrate:
        config.AUDIO_BITRATE = parsed_args.bitrate

    if parsed_args.open:
        config.AUTO_OPEN_AUDIO = True

    if parsed_args.force_ocr:
        config.ENABLE_OCR_FALLBACK = True

    if parsed_args.disable_multicolumn:
        config.ENABLE_MULTICOLUMN_DETECTION = False

    if parsed_args.keep_citations:
        config.CLEAN_ACADEMIC_CITATIONS = False