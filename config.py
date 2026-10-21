# --------------- TTS ---------------
# - "en-US-BrianNeural" (Male) & "en-US-AvaNeural" (Female)
VOICE = "en-US-BrianNeural"
MAX_TTS_CHARS = 3000
SPEECH_RATE = "+0%"
SPEECH_VOLUME = "+0%"
SPEECH_PITCH = "+0Hz"

# Number of parallel TTS requests to process concurrently (recommended: 3 to 5)
MAX_CONCURRENT_REQUESTS = 4

# Set to a number while testing. Set to None for the complete book.
MAX_SECTIONS = None

# --------------- Output ---------------
OUTPUT_EXTENSION = ".mp4"
AUDIO_BITRATE = "320k"

# Automatically open the finished audiobook.
AUTO_OPEN_AUDIO = False

# None = same folder as selected PDF. Otherwise specify the desired output directory.
OUTPUT_DIRECTORY = None

# --------------- Subtitles ---------------
SUBTITLE_FORMAT = "mov_text"
MAX_SUBTITLE_CHARS = 45
MAX_SUBTITLE_DURATION_MS = 4000
MAX_SUBTITLE_WORDS = 8

# True  = embed timed captions in the MP4; False = normal audiobook without captions.
ENABLE_SUBTITLES = True

# True  = subtitles visible on launch; False = subtitles disabled on launch
SUBTITLES_DEFAULT_ON = True

# --------------- Images & Visual Slides --------------- 
ENABLE_IMAGE_EXTRACTION = True
MIN_IMAGE_WIDTH = 100
MIN_IMAGE_HEIGHT = 100
MAX_IMAGE_ASPECT_RATIO = 5.0
ENABLE_IMAGE_OCR = True
SLIDE_WIDTH = 1280
SLIDE_HEIGHT = 720

# --------------- PDF ---------------
ENABLE_OCR_FALLBACK = True
OCR_LANGUAGE = "eng"
MIN_TEXT_CHARS = 40
USE_PDF_TOC = True
VALIDATE_TOC = True

# --------------- Academic & Layout Processing ---------------
# True  = detect multi-column layouts (2 or 3 columns in research papers/textbooks) and sort reading order
ENABLE_MULTICOLUMN_DETECTION = True

# True  = clean citations like [1, 2], (Smith et al., 2020), URLs, and LaTeX notation for natural speech
CLEAN_ACADEMIC_CITATIONS = True

# --------------- Section Filtering ---------------
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
    "references",
    "reference",
    "bibliography",
    "works cited",
    "literature cited",
    "citations",
    "index",
    "further reading",
}

# Titles beginning with these phrases are also excluded.
EXCLUDED_SECTION_PREFIXES = {
    "books by ",
    "also by ",
    "about the publisher",
    "about the author",
    "references",
    "bibliography",
    "works cited",
}

IGNORED_TEXT = {"oceanpdf.com",}

# --------------- Checkpoints & Resume ---------------
# True  = persist audio chunks and resume interrupted conversions without starting over
ENABLE_CHECKPOINTS = True

# Custom directory for checkpoints. If None, stores in '.audiobook_cache' in output folder
CHECKPOINT_DIRECTORY = None

# True  = remove individual chunk files after the final MP4 is completely built & verified; False = keep chunk files for instant re-encodes (e.g. changing bitrate or subtitles)
CLEANUP_CHUNKS_ON_SUCCESS = False

# --------------- Debugging ---------------
# False = remove temporary individual TTS files; True  = keep them for debugging.
KEEP_TTS_SEGMENTS = False