from pathlib import Path
import sys
from tqdm import tqdm

def show_banner():
    print()
    print("=" * 60)
    print("PDF TO AUDIOBOOK CONVERTER")
    print("=" * 60)
    print()

def select_pdf(cli_pdf_path: str | Path | None = None) -> Path | None:
    if cli_pdf_path:
        arg_path = Path(cli_pdf_path)
        if arg_path.exists() and arg_path.is_file():
            return arg_path

        show_error(f"Provided PDF file not found: {cli_pdf_path}")
        return None

    try:
        from tkinter import Tk, filedialog
        root = Tk()
        root.withdraw()
        file_path = filedialog.askopenfilename(title="Select the PDF", filetypes=[("PDF files", "*.pdf")],)
        root.destroy()
        if not file_path:
            return None

        return Path(file_path)

    except Exception:
        return None

def show_selected_file(filename: str):
    print(f"Selected PDF: {filename}\n")

def show_info(message: str):
    print(f"  [Info] {message}")

def show_ocr_fallback(total_pages: int, reason: str = "Scanned/Image-based PDF detected"):
    print(f"  {reason}! Performing RapidOCR text recognition on {total_pages} pages...")

def show_step_start(step_num: int, total_steps: int, title: str):
    print(f"[Step {step_num}/{total_steps}] {title}")

def show_step_done(step_num: int, total_steps: int, title: str):
    print(f"[Step {step_num}/{total_steps}] {title}... [Done]\n")

def show_book_metadata(title: str, author: str, section_count: int, image_count: int = 0):
    print(f"  Title: {title}")
    print(f"  Author: {author}")
    print(f"  Narrative Sections: {section_count}")
    if image_count > 0:
        print(f"  Visual Diagrams/Images: {image_count} detected (OCR & paragraph sync enabled)")

    else:
        print("  Visual Diagrams/Images: None (Standard visual canvas)")

def show_checkpoint_found(cached_sections: int, total_sections: int, cached_steps: int, total_steps: int):
    pct = (cached_steps / max(1, total_steps)) * 100
    print(f"  Checkpoint: Resuming active session ({pct:.0f}% already cached)")
    print(f"  Progress: {cached_sections}/{total_sections} sections completed, {cached_steps}/{total_steps} chunks ready\n")

def show_warning(message: str):
    print(f"\n{message}\n")

def show_error(message: str):
    print(f"\nERROR: {message}\n")

def show_completion(output_path: Path, duration_minutes: float, bitrate: str, subtitles_enabled: bool, slides_count: int = 0):
    print("=" * 60)
    print("AUDIOBOOK COMPLETE")
    print("=" * 60)
    print()
    print(f"Output: {output_path}")
    print(f"Duration: {duration_minutes:.1f} minutes")
    print(f"Audio Bitrate: {bitrate}")
    if subtitles_enabled:
        print("Subtitles: Enabled (Toggleable in media player CC menu)")

    else:
        print("Subtitles: Disabled")

    if slides_count > 0:
        print(f"Visual Slides: {slides_count} slides synchronized to chapters & paragraphs")

    else:
        print("Visual Slides: Standard canvas")

    print()

class OCRProgress:
    # Context manager for full-page OCR progress bar across scanned pages.
    def __init__(self, total_pages: int):
        self.total_pages = max(1, total_pages)
        self.pbar = None

    def __enter__(self):
        self.pbar = tqdm(total=self.total_pages, desc="OCR Scanning", unit="page", bar_format="{desc}: {percentage:3.0f}%|{bar}| {n_fmt}/{total_fmt} pages [{elapsed} elapsed, {remaining} remaining]", dynamic_ncols=True,)
        return self

    def update_page(self, page_num: int):
        if self.pbar:
            self.pbar.update(1)

    def __exit__(self, exc_type, exc_val, exc_tb):
        if self.pbar:
            self.pbar.close()

class NarrationProgress:
    # Context manager for the chunk-by-chunk audiobook narration progress bar. Displays percentage, chunk counts, human-readable elapsed/remaining time, and active section/chunk context.
    def __init__(self, total_steps: int, initial_steps: int = 0):
        self.total_steps = max(1, total_steps)
        self.initial_steps = initial_steps
        self.pbar = None

    def __enter__(self):
        self.pbar = tqdm(total=self.total_steps, initial=self.initial_steps, desc="Narration", unit="chunk", bar_format="{desc}: {percentage:3.0f}%|{bar}| {n_fmt}/{total_fmt} chunks [{elapsed} elapsed, {remaining} remaining{postfix}]", dynamic_ncols=True,)
        return self

    def update_chunk(self, section_num: int, total_sections: int, section_title: str, step_desc: str):
        if self.pbar:
            self.pbar.update(1)
            sec_label = section_title[:20]
            self.pbar.set_postfix_str(f"[{section_num}/{total_sections}] {sec_label} - {step_desc}")

    def __exit__(self, exc_type, exc_val, exc_tb):
        if self.pbar:
            self.pbar.close()

class EncodingProgress:
    # Context manager for the final MP4 encoding progress bar. Suppresses raw FFmpeg terminal dumps and shows a clean, quiet progress bar.
    def __init__(self, total_seconds: int):
        self.total_seconds = max(1, total_seconds)
        self.pbar = None

    def __enter__(self):
        self.pbar = tqdm(total=self.total_seconds, desc="Encoding MP4", unit="s", bar_format="{desc}: {percentage:3.0f}%|{bar}| [{elapsed} elapsed, {remaining} remaining]", dynamic_ncols=True,)
        return self

    def update_seconds(self, delta_s: float):
        if self.pbar:
            self.pbar.update(min(delta_s, self.total_seconds - self.pbar.n))

    def __exit__(self, exc_type, exc_val, exc_tb):
        if self.pbar:
            if self.pbar.n < self.pbar.total:
                self.pbar.update(self.pbar.total - self.pbar.n)
            self.pbar.close()