# LuminaRead
LuminaRead converts PDF documents, books, research papers, and reports into high-fidelity audiobooks with synchronized visual slides and dialogue-level subtitles. It leverages Microsoft Edge Neural Text-to-Speech (TTS), PyMuPDF for document and diagram extraction, RapidOCR for visual text analysis, and FFmpeg for high-bitrate AAC audio, chapter bookmarking, and video slide transitions.

## Features
- Extracts chapters and narrative sections automatically using table of contents or content heuristics.
- Synthesizes speech using Microsoft Edge Neural TTS with sentence-level phrasing and dialogue synchronization.
- Extracts visual diagrams, graphs, flowcharts, and illustrations from PDF pages.
- Performs on-device OCR on visual elements using RapidOCR without external system dependencies.
- Generates a single high-quality MP4 audiobook containing 320k AAC audio, clickable chapter bookmarks, and toggleable soft subtitles (`mov_text`).
- Dynamically aligns visual slides to chapters and paragraphs, keeping relevant diagrams on screen during narration.
- Multi-worker concurrent narration and lossless FFmpeg audio assembly for fast conversion.

## Usage
### All required libraries can be installed using a single-line command:
```bash
pip install -r requirements.txt
```

### While to run the code:
#### Direct execution:
```bash
# Opens GUI file picker
python main.py

# Or pass the PDF path directly
python main.py "path/to/book.pdf"
```

#### Docker-based version:
```bash
# Build the Docker image
docker build -t audiobook-converter .

# Run conversion on a PDF file
docker run --rm -v "C:/path/to/pdfs:/data" audiobook-converter /data/book.pdf
```

## Description about various files:
- **audiobook.py:** Handles audio concatenation, chapter metadata generation (`FFMETADATA1`), subtitle track formatting (SRT), and final MP4 encoding via FFmpeg.
- **config.py:** Centralized configuration file for TTS voice parameters, audio bitrate, subtitle options, and image extraction/OCR settings.
- **Dockerfile:** Container definition packaging Python 3.11, FFmpeg, OpenCV, and all project dependencies for consistent cross-platform execution.
- **image_processor.py:** Extracts images and diagrams from PDFs, performs OCR text analysis, formats 16:9 visual slides, and synchronizes slide timelines with narration.
- **main.py:** Main runner and orchestrator that coordinates PDF analysis, introduction synthesis, parallel narration, and final media encoding.
- **narrator.py:** Coordinates parallel chunk synthesis using worker semaphores and gathers audio segments, subtitle cues, and chunk durations.
- **pdf_processor.py:** Extracts metadata, analyzes page text, filters out repeated headers/footers, and detects chapters and narrative sections.
- **requirements.txt:** File containing all required Python modules.
- **text_processor.py:** Cleans text, breaks content into sentence-aware TTS chunks, and groups word boundary events into natural dialogue subtitle cues.
- **tts_engine.py:** Interfaces with Microsoft Edge TTS to synthesize audio chunks and capture word-level timing metadata.
- **ui.py:** Manages user interaction, PDF file selection dialog, metadata displays, and quiet terminal progress bars.
