# LuminaRead
LuminaRead converts PDF documents, books, research papers, and reports into high-fidelity audiobooks with synchronised visual slides and dialogue-level subtitles. It leverages Microsoft Edge Neural Text-to-Speech (TTS), PyMuPDF for document and diagram extraction, RapidOCR for visual text analysis, and FFmpeg for high-bitrate AAC audio, chapter bookmarking, and video slide transitions.

## Features
- Extracts chapters and narrative sections automatically using table of contents or content heuristics.
- Synthesises speech using Microsoft Edge Neural TTS with sentence-level phrasing and dialogue synchronisation.
- Scanned PDF fallback with on-device RapidOCR that automatically recognizes text from image-only scans and hybrid documents.
- Multi-column and complex layout extraction that dynamically detects 2-column or 3-column structures in research papers and textbooks, preventing interleaved sentences.
- Academic and reference cleaner that cleans bracketed citations (`[1, 2]`), author-year tags (`(Vaswani et al., 2017)`), footnote markers, raw URLs, and LaTeX math for natural speech flow, while automatically excluding bibliography sections.
- Extracts visual diagrams, graphs, flowcharts, and illustrations from PDF pages.
- Performs on-device OCR on visual elements using RapidOCR without external system dependencies.
- Generates a single high-quality MP4 audiobook containing 320k AAC audio, clickable chapter bookmarks, and toggleable soft subtitles (`mov_text`).
- Dynamically aligns visual slides to chapters and paragraphs, keeping relevant diagrams on screen during narration.
- Multi-worker concurrent narration and lossless FFmpeg audio assembly for fast conversion.
- Fault-tolerant checkpointing and atomic write recovery that caches progress per chunk, section, and OCR page, allowing interrupted conversions to resume seamlessly without redundant processing.
- Flexible command-line interface with runtime options for voices, narration speeds, worker concurrency, and testing limits.

## Usage
### All required libraries can be installed using a single-line command:
```bash
pip install -r requirements.txt
```

### To run the code:
#### Direct execution:
```bash
# Opens graphical file picker
python main.py

# Or pass the PDF path directly
python main.py "path/to/book.pdf"
```

#### Docker-based version:
```bash
# Build the Docker image
docker build -t LuminaRead .

# Run conversion on a PDF file
docker run --rm -v "C:/path/to/pdfs:/data" LuminaRead /data/book.pdf
```

## Command-Line Options (CLI Flags)
LuminaRead can be customized using command-line arguments:

| Option | Shorthand | Default | Description |
| :--- | :--- | :--- | :--- |
| `pdf` | — | Graphical picker | Path to the PDF file. If omitted, opens the file selection dialog. |
| `--voice` | `-v` | `en-US-BrianNeural` | Neural TTS voice model (e.g. `en-US-BrianNeural`, `en-US-AvaNeural`, `en-US-AndrewNeural`, `en-US-EmmaNeural`). |
| `--speed` | `-s` | `+0%` | Narration speed adjustment (e.g. `+10%`, `-5%`, or multiplier `1.25` for 1.25x speed). |
| `--output` | `-o` | Input PDF folder | Directory to save the final MP4 audiobook. |
| `--sections` | `-n` | All sections | Limit conversion to the first *N* sections (ideal for quick tests and previews). |
| `--workers` | `-w` | `4` | Number of concurrent TTS synthesis workers (recommended: 3 to 5). |
| `--ocr` / `--force-ocr` | — | `False` | Force full-page OCR text recognition on all pages using RapidOCR. |
| `--no-images` | — | `False` | Disable diagram/image extraction and narrate with a clean visual canvas. |
| `--no-subtitles` | — | `False` | Disable timed subtitle generation and embedding in the final MP4. |
| `--no-cache` / `--force-restart` | — | `False` | Disregard existing checkpoints and synthesize from scratch. |
| `--bitrate` | `-b` | `320k` | Audio bitrate for final MP4 audio stream (e.g. `192k`, `320k`). |
| `--open` | — | `False` | Automatically launch the finished audiobook in your default media player when complete. |
| `--no-layout` | — | `False` | Disable multi-column layout analysis and extract text strictly top-to-bottom. |
| `--keep-citations` | — | `False` | Keep raw academic citations (e.g. `[1, 2]`, `(Smith, 2020)`) and URLs instead of cleaning them for speech. |

### CLI Examples:
```bash
# Convert a 2-column research paper with academic citation cleaning
python main.py paper.pdf

# Convert a scanned book with full-page OCR
python main.py scanned_book.pdf --ocr

# Quick 1-chapter preview with female narrator at 1.25x speed
python main.py novel.pdf -n 1 --voice en-US-AvaNeural --speed 1.25

# Audio-only conversion without image slides or subtitles
python main.py report.pdf --no-images --no-subtitles

# Convert with 5 parallel workers and save to a custom output folder
python main.py textbook.pdf -w 5 -o "D:/Audiobooks"

# Force fresh synthesis bypassing existing cache
python main.py paper.pdf --no-cache
```

## Description of various files:
- **audiobook.py:** Handles audio concatenation, chapter metadata generation (`FFMETADATA1`), subtitle track formatting (SRT), and final MP4 encoding via FFmpeg.
- **checkpoint_manager.py:** Manages fault-tolerant state persistence, atomic chunk writing, corrupted cache detection, and seamless resumption of audio, subtitles, and extracted visual slides.
- **cli.py:** Command-line interface parser that handles argument parsing, speed normalization, and runtime configuration overrides.
- **config.py:** Centralised configuration file for TTS voice parameters, audio bitrate, subtitle options, and image extraction/OCR settings.
- **Dockerfile:** Container definition packaging Python 3.11, FFmpeg, OpenCV, and all project dependencies for consistent cross-platform execution.
- **image_processor.py:** Extracts images and diagrams from PDFs, performs OCR text analysis, formats 16:9 visual slides, and synchronises slide timelines with narration.
- **main.py:** Main runner and orchestrator that coordinates PDF analysis, introduction synthesis, parallel narration, and final media encoding.
- **narrator.py:** Coordinates parallel chunk synthesis using worker semaphores and gathers audio segments, subtitle cues, and chunk durations.
- **pdf_processor.py:** Extracts metadata, analyses page text, detects multi-column layouts, cleans headers/footers, detects narrative sections, and handles automatic RapidOCR fallback for scanned pages.
- **requirements.txt:** File containing all required Python modules.
- **text_processor.py:** Cleans academic citations, breaks content into sentence-aware TTS chunks, and groups word boundary events into natural dialogue subtitle cues.
- **tts_engine.py:** Interfaces with Microsoft Edge TTS to synthesise audio chunks and capture word-level timing metadata.
- **ui.py:** Manages user interaction, PDF file selection dialogue, metadata displays, OCR scanning progress bars, and quiet terminal progress bars.
