# -----------------------------
# TTS
# -----------------------------

VOICE = "en-US-AriaNeural"
MAX_TTS_CHARS = 3000
SPEECH_RATE = "+0%"
SPEECH_VOLUME = "+0%"
SPEECH_PITCH = "+0Hz"

# Number of parallel TTS requests to process concurrently (recommended: 3 to 5)
MAX_CONCURRENT_REQUESTS = 4

# Set to a number while testing. Set to None for the complete book.
MAX_SECTIONS = None

# -----------------------------
# OUTPUT
# -----------------------------

OUTPUT_EXTENSION = ".mp4"
AUDIO_BITRATE = "320k"

# Automatically open the finished audiobook.
AUTO_OPEN_AUDIO = False

# None = same folder as selected PDF. Otherwise specify the desired output directory.
OUTPUT_DIRECTORY = None

# -----------------------------
# SUBTITLES
# -----------------------------

SUBTITLE_FORMAT = "mov_text"

# True  = embed timed captions in the MP4; False = normal audiobook without captions.
ENABLE_SUBTITLES = True

# Natural phrase constraints for dialogue-synchronized subtitles
MAX_SUBTITLE_WORDS = 8
MAX_SUBTITLE_CHARS = 45
MAX_SUBTITLE_DURATION_MS = 4000

# -----------------------------
# PDF
# -----------------------------

# Reserved for future OCR implementation.
ENABLE_OCR_FALLBACK = True
OCR_LANGUAGE = "eng"
MIN_TEXT_CHARS = 40
USE_PDF_TOC = True
VALIDATE_TOC = True

# -----------------------------
# Section filtering
# -----------------------------

EXCLUDED_SECTIONS = {
    "contents",
    "table of contents",
    "acknowledgments",
    "acknowledgements",
    "about the author",
    "about the publisher",
    "also by",
    "copyright",
    "copyright page",
    "title page",
    "back ad",
    "back cover",
    "cover",
}

# Titles beginning with these phrases are also excluded.
EXCLUDED_SECTION_PREFIXES = {
    "books by ",
    "also by ",
    "about the publisher",
    "about the author",
}

IGNORED_TEXT = {"oceanpdf.com",}

# -----------------------------
# Debugging
# -----------------------------

# False = remove temporary individual TTS files; True  = keep them for debugging.
KEEP_TTS_SEGMENTS = False