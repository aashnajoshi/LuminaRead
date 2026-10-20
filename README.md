# PDF to Audiobook Converter

A Python-based PDF to audiobook converter using Microsoft Edge neural TTS.

## Features

- PDF file selection
- PDF metadata extraction
- PDF table-of-contents detection
- Automatic narrative section detection
- Section/chapter filtering
- Neural Microsoft TTS
- Sentence-aware TTS chunking
- Chapter titles spoken separately
- Pause after chapter titles
- High-bitrate AAC MP4 output with black canvas
- Clickable chapter bookmarks
- Dialogue-synchronized toggleable soft subtitles (CC)
- Configurable voice and 320k audio bitrate
- Configurable output directory
- Test mode using a limited number of sections

## Project Structure

```text
Audiobook/
│
├── main.py
├── ui.py
├── config.py
├── pdf_processor.py
├── text_processor.py
├── tts_engine.py
├── narrator.py
├── audiobook.py
├── requirements.txt
└── README.md
```
