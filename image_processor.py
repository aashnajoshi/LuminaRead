from dataclasses import dataclass, field
from pathlib import Path
from typing import Any
import pymupdf as fitz
from PIL import Image
from config import (
    ENABLE_IMAGE_EXTRACTION,
    ENABLE_IMAGE_OCR,
    MAX_IMAGE_ASPECT_RATIO,
    MIN_IMAGE_HEIGHT,
    MIN_IMAGE_WIDTH,
    SLIDE_HEIGHT,
    SLIDE_WIDTH,
)

_ocr_engine = None

def _get_ocr_engine():
    global _ocr_engine
    if _ocr_engine is None:
        try:
            from rapidocr_onnxruntime import RapidOCR
            _ocr_engine = RapidOCR()

        except Exception:
            _ocr_engine = False

    return _ocr_engine if _ocr_engine is not False else None

@dataclass
class ExtractedImage:
    image_path: Path
    page_number: int
    y0: float
    y1: float
    width: int
    height: int
    ocr_text: str = ""

@dataclass
class SlideSegment:
    image_path: Path
    duration_seconds: float

def create_blank_canvas(output_path: Path, width: int = SLIDE_WIDTH, height: int = SLIDE_HEIGHT) -> Path:
    if not output_path.exists():
        canvas = Image.new("RGB", (width, height), color=(0, 0, 0))
        canvas.save(output_path, "PNG")

    return output_path

def format_slide_image(raw_img_path: Path, output_path: Path, width: int = SLIDE_WIDTH, height: int = SLIDE_HEIGHT, subtitle_margin_bottom: int = 120,) -> Path:
    with Image.open(raw_img_path) as img:
        img = img.convert("RGB")
        max_w = width - 80
        max_h = height - subtitle_margin_bottom - 40
        img_w, img_h = img.size
        scale = min(max_w / img_w, max_h / img_h)
        new_w = max(1, int(img_w * scale))
        new_h = max(1, int(img_h * scale))
        resized = img.resize((new_w, new_h), Image.Resampling.LANCZOS)
        canvas = Image.new("RGB", (width, height), color=(0, 0, 0))
        pos_x = (width - new_w) // 2
        pos_y = max(20, (height - subtitle_margin_bottom - new_h) // 2 + 10)
        canvas.paste(resized, (pos_x, pos_y))
        canvas.save(output_path, "PNG")
        return output_path

def run_image_ocr(image_path: Path) -> str:
    if not ENABLE_IMAGE_OCR:
        return ""

    engine = _get_ocr_engine()
    if not engine:
        return ""

    try:
        results, _ = engine(str(image_path))
        if not results:
            return ""

        extracted = [box[1].strip() for box in results if len(box) > 1 and box[1].strip()]
        return " ".join(extracted)

    except Exception:
        return ""

def extract_images_from_pdf(pdf_path: Path, temp_directory: Path) -> list[ExtractedImage]:
    if not ENABLE_IMAGE_EXTRACTION:
        return []

    doc = fitz.open(pdf_path)
    extracted_images: list[ExtractedImage] = []
    slides_dir = temp_directory / "slides"
    slides_dir.mkdir(parents=True, exist_ok=True)
    try:
        total_pages = len(doc)
        xref_page_counts: dict[int, int] = {}
        for page in doc:
            for item in page.get_images(full=True):
                xref = item[0]
                xref_page_counts[xref] = xref_page_counts.get(xref, 0) + 1

        repeated_threshold = max(4, int(total_pages * 0.20))
        repeated_xrefs = {xref for xref, count in xref_page_counts.items() if count >= repeated_threshold}
        seen_images_per_page: set[tuple[int, int]] = set()
        for page_index in range(total_pages):
            page_number = page_index + 1
            page = doc[page_index]
            page_height = page.rect.height or 800.0
            image_list = page.get_images(full=True)
            for img_index, img_item in enumerate(image_list):
                xref = img_item[0]
                if xref in repeated_xrefs:
                    continue

                if (page_number, xref) in seen_images_per_page:
                    continue

                seen_images_per_page.add((page_number, xref))
                try:
                    pix = fitz.Pixmap(doc, xref)

                except Exception:
                    continue

                orig_w = pix.width
                orig_h = pix.height
                if orig_w < MIN_IMAGE_WIDTH or orig_h < MIN_IMAGE_HEIGHT:
                    continue

                aspect_ratio = max(orig_w / max(1, orig_h), orig_h / max(1, orig_w))
                if aspect_ratio > MAX_IMAGE_ASPECT_RATIO:
                    continue

                raw_filename = f"raw_p{page_number:04d}_{img_index:02d}_{xref}.png"
                raw_path = slides_dir / raw_filename
                if pix.n >= 5:
                    pix_rgb = fitz.Pixmap(fitz.csRGB, pix)
                    pix_rgb.save(raw_path)
                    pix_rgb = None

                else:
                    pix.save(raw_path)

                rects = page.get_image_rects(xref)
                if rects:
                    y0 = rects[0].y0
                    y1 = rects[0].y1

                else:
                    y0 = (page_height / max(1, len(image_list))) * img_index
                    y1 = y0 + 100.0

                ocr_text = run_image_ocr(raw_path)
                slide_filename = f"slide_p{page_number:04d}_{img_index:02d}_{xref}.png"
                slide_path = slides_dir / slide_filename
                format_slide_image(raw_path, slide_path)
                extracted_images.append(
                    ExtractedImage(image_path=slide_path, page_number=page_number, y0=y0, y1=y1, width=orig_w, height=orig_h, ocr_text=ocr_text,))

        extracted_images.sort(key=lambda item: (item.page_number, item.y0))
        return extracted_images

    finally:
        doc.close()

def build_slide_timeline(sections: list[Any], section_durations_ms: list[int], section_chunk_durations_ms: list[list[int]], extracted_images: list[ExtractedImage], intro_duration_ms: int, temp_directory: Path,) -> list[SlideSegment]:
    blank_canvas = create_blank_canvas(temp_directory / "blank_canvas.png")
    timeline: list[SlideSegment] = []
    # --------------- 1. Introduction Slide ---------------
    intro_duration_sec = intro_duration_ms / 1000.0
    cover_image = None
    if extracted_images and extracted_images[0].page_number <= 2:
        cover_image = extracted_images[0].image_path

    if cover_image:
        timeline.append(SlideSegment(image_path=cover_image, duration_seconds=intro_duration_sec))

    else:
        timeline.append(SlideSegment(image_path=blank_canvas, duration_seconds=intro_duration_sec))

    # --------------- 2. Section Slides --------------- 
    for sec_idx, section in enumerate(sections):
        sec_duration_sec = section_durations_ms[sec_idx] / 1000.0
        if sec_duration_sec <= 0:
            continue

        chunk_durations = [ms / 1000.0 for ms in section_chunk_durations_ms[sec_idx]]
        sec_images = [img for img in extracted_images if section.start_page <= img.page_number <= section.end_page]
        # --------------- Case 0: No images in this section -> Blank canvas ---------------
        if not sec_images:
            timeline.append(SlideSegment(image_path=blank_canvas, duration_seconds=sec_duration_sec))
            continue

        # --------------- Case 1: Exactly 1 image in chapter -> Display for entire chapter duration ---------------
        if len(sec_images) == 1:
            timeline.append(SlideSegment(image_path=sec_images[0].image_path, duration_seconds=sec_duration_sec))
            continue

        # --------------- Case 2: Multiple images -> Map to chunks/paragraphs ---------------
        num_chunks = len(chunk_durations)
        page_span = max(1, section.end_page - section.start_page + 1)
        chunk_start_times = [0.0]
        accum = 0.0
        for dur in chunk_durations:
            accum += dur
            chunk_start_times.append(accum)

        mapped_chunks: list[int] = []
        for img in sec_images:
            norm_pos = (img.page_number - section.start_page) / page_span
            target_chunk = min(max(0, num_chunks - 1), int(norm_pos * num_chunks))
            mapped_chunks.append(target_chunk)

        for i in range(1, len(mapped_chunks)):
            if mapped_chunks[i] <= mapped_chunks[i - 1] and mapped_chunks[i - 1] < num_chunks - 1:
                mapped_chunks[i] = mapped_chunks[i - 1] + 1

        starts = [chunk_start_times[min(c, num_chunks)] for c in mapped_chunks]
        if starts[0] > 0.5 and sec_images[0].page_number > section.start_page:
            timeline.append(SlideSegment(image_path=blank_canvas, duration_seconds=starts[0]))

        else:
            starts[0] = 0.0

        for i in range(len(sec_images) - 1):
            cur_start = starts[i]
            next_start = starts[i + 1]
            seg_dur = max(0.1, next_start - cur_start)
            timeline.append(SlideSegment(image_path=sec_images[i].image_path, duration_seconds=seg_dur))

        last_start = starts[-1]
        last_dur = max(0.1, sec_duration_sec - last_start)
        timeline.append(SlideSegment(image_path=sec_images[-1].image_path, duration_seconds=last_dur))

    return timeline

def create_slides_manifest(slide_segments: list[SlideSegment], output_path: Path) -> Path:
    lines: list[str] = []
    for segment in slide_segments:
        if segment.duration_seconds <= 0:
            continue

        lines.append(f"file '{segment.image_path.as_posix()}'")
        lines.append(f"duration {segment.duration_seconds:.3f}")

    if slide_segments:
        lines.append(f"file '{slide_segments[-1].image_path.as_posix()}'")

    output_path.write_text("\n".join(lines), encoding="utf-8")
    return output_path