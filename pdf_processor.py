from dataclasses import dataclass
from pathlib import Path
import re
import pymupdf as fitz
from checkpoint_manager import load_scanned_page_texts_cache, save_scanned_page_texts_cache
import config
from text_processor import clean_academic_text

@dataclass
class Section:
    title: str
    start_page: int
    end_page: int
    text: str

def normalize_title(title: str) -> str:
    return " ".join(title.lower().split())

def clean_text(text: str) -> str:
    if not text:
        return ""

    text = text.replace("\xa0", " ")
    for ignored in config.IGNORED_TEXT:
        text = text.replace(ignored, "")

    text = text.replace("-\n", "")
    text = text.replace("\r\n", "\n")
    text = text.replace("\r", "\n")
    text = text.replace("\n", " ")
    text = " ".join(text.split())
    if config.CLEAN_ACADEMIC_CITATIONS:
        text = clean_academic_text(text)

    return text.strip()

def get_metadata(pdf, pdf_path: Path):
    metadata = pdf.metadata or {}
    title = metadata.get("title") or pdf_path.stem
    author = metadata.get("author") or "Unknown"
    title = title.strip() or pdf_path.stem
    author = author.strip() or "Unknown"
    return title, author

def find_gutter(lines: list[dict], min_gap: float = 4.0) -> float | None:
    """Finds an empty vertical gutter that cleanly divides lines into distinct columns with zero crossings."""
    if len(lines) < 2:
        return None

    x_splits = sorted(set([round(l["bbox"][2], 1) for l in lines] + [round(l["bbox"][0], 1) for l in lines]))
    candidates = []
    for i in range(len(x_splits) - 1):
        gap = x_splits[i + 1] - x_splits[i]
        if gap < min_gap:
            continue

        gx = (x_splits[i] + x_splits[i + 1]) / 2.0
        left = [l for l in lines if l["bbox"][2] <= gx]
        right = [l for l in lines if l["bbox"][0] >= gx]
        cross = [l for l in lines if l["bbox"][0] < gx < l["bbox"][2]]
        if len(cross) == 0 and len(left) >= 1 and len(right) >= 1:
            candidates.append((gx, min(len(left), len(right)), gap))

    if not candidates:
        return None

    candidates.sort(key=lambda item: (item[1], item[2]), reverse=True)
    return candidates[0][0]

def sort_band(lines: list[dict]) -> list[dict]:
    """Recursively sorts lines within a vertical band across multiple columns."""
    if len(lines) < 2:
        return sorted(lines, key=lambda l: l["bbox"][1])

    gx = find_gutter(lines)
    if gx is not None:
        col_left = [l for l in lines if l["bbox"][2] <= gx]
        col_right = [l for l in lines if l["bbox"][0] >= gx]
        col_mid = [l for l in lines if l not in col_left and l not in col_right]
        return sort_band(col_left) + sort_band(col_right) + sorted(col_mid, key=lambda l: l["bbox"][1])

    return sorted(lines, key=lambda l: l["bbox"][1])

def order_lines_by_layout(lines: list[dict], page_width: float) -> list[dict]:
    """Orders text lines taking into account full-width elements and multi-column bands."""
    if not lines:
        return []

    full_threshold = 0.60 * page_width
    sorted_y = sorted(lines, key=lambda l: l["bbox"][1])
    bands = []
    cur_band = []
    for l in sorted_y:
        x0, y0, x1, y1 = l["bbox"]
        w = x1 - x0
        is_full = w >= full_threshold or (x0 < 0.40 * page_width and x1 > 0.60 * page_width)
        if is_full:
            if cur_band:
                bands.append(("multi", cur_band))
                cur_band = []

            bands.append(("full", [l]))

        else:
            cur_band.append(l)

    if cur_band:
        bands.append(("multi", cur_band))

    ordered = []
    for b_type, b_lines in bands:
        if b_type == "full":
            ordered.extend(b_lines)

        else:
            ordered.extend(sort_band(b_lines))

    return ordered

def extract_page_layout_text(page) -> str:
    """Extracts text from a page, applying layout analysis for multi-column documents."""
    if not config.ENABLE_MULTICOLUMN_DETECTION:
        return page.get_text("text") or ""

    try:
        dict_data = page.get_text("dict")
        lines = []
        for b in dict_data.get("blocks", []):
            if b.get("type") == 0:
                for l in b.get("lines", []):
                    line_text = "".join(s.get("text", "") for s in l.get("spans", [])).strip()
                    if line_text:
                        lines.append({"bbox": l["bbox"], "text": line_text})

        if not lines:
            return ""

        page_width = page.rect.width
        ordered = order_lines_by_layout(lines, page_width)
        return "\n".join(l["text"] for l in ordered)

    except Exception:
        return page.get_text("text") or ""

def extract_page_text(page) -> str:
    return extract_page_layout_text(page)

def extract_all_page_text(pdf) -> list[str]:
    return [extract_page_text(page) for page in pdf]

def ocr_page(page, dpi: int = 150) -> str:
    """Renders a PDF page to image and performs OCR text recognition using RapidOCR with column layout sorting."""
    try:
        from image_processor import _get_ocr_engine
        engine = _get_ocr_engine()
        if not engine:
            return ""

        pix = page.get_pixmap(dpi=dpi)
        results, _ = engine(pix.tobytes("png"))
        if not results:
            return ""

        raw_lines = []
        for item in results:
            if len(item) > 1 and item[1].strip():
                box = item[0]
                x0 = min(pt[0] for pt in box)
                y0 = min(pt[1] for pt in box)
                x1 = max(pt[0] for pt in box)
                y1 = max(pt[1] for pt in box)
                raw_lines.append({"bbox": (x0, y0, x1, y1), "text": item[1].strip()})

        if not raw_lines:
            return ""

        if config.ENABLE_MULTICOLUMN_DETECTION:
            ordered = order_lines_by_layout(raw_lines, pix.width)
            return "\n".join(l["text"] for l in ordered)

        else:
            return "\n".join(l["text"] for l in raw_lines)

    except Exception:
        return ""

def detect_repeated_edge_text(page_texts):
    first_lines = {}
    last_lines = {}
    for text in page_texts:
        lines = [line.strip() for line in text.splitlines() if line.strip()]
        if not lines:
            continue

        first = normalize_title(lines[0])
        last = normalize_title(lines[-1])
        first_lines[first] = first_lines.get(first, 0) + 1
        last_lines[last] = last_lines.get(last, 0) + 1

    threshold = max(3, len(page_texts) // 20)
    repeated_first = {value for value, count in first_lines.items() if count >= threshold}
    repeated_last = {value for value, count in last_lines.items() if count >= threshold}
    return repeated_first, repeated_last

def remove_page_numbers(text: str) -> str:
    lines = text.splitlines()
    cleaned = []
    for line in lines:
        stripped = line.strip()
        if not stripped:
            continue

        if stripped.isdigit():
            continue

        if (stripped.lower().startswith("page ") and stripped[5:].strip().isdigit()):
            continue

        cleaned.append(line)

    return "\n".join(cleaned)

def remove_repeated_edge_lines(text: str, repeated_first: set[str], repeated_last: set[str]) -> str:
    lines = [line for line in text.splitlines() if line.strip()]
    if not lines:
        return ""

    if normalize_title(lines[0]) in repeated_first:
        lines = lines[1:]

    if lines and normalize_title(lines[-1]) in repeated_last:
        lines = lines[:-1]

    return "\n".join(lines)

def clean_page(text: str, repeated_first: set[str], repeated_last: set[str]) -> str:
    text = remove_page_numbers(text)
    text = remove_repeated_edge_lines(text, repeated_first, repeated_last)
    return text

def get_top_level_toc(pdf):
    toc = pdf.get_toc(simple=True)
    if not toc:
        return []

    entries = []
    for level, title, page in toc:
        if level != 1:
            continue

        if not title:
            continue

        entries.append({"title": title.strip(), "page": max(1, page)})

    return entries

def validate_toc_entries(toc_entries, page_texts):
    if not config.VALIDATE_TOC:
        return toc_entries

    validated = []
    for entry in toc_entries:
        page_index = entry["page"] - 1
        if page_index < 0 or page_index >= len(page_texts):
            continue

        page_text = normalize_title(page_texts[page_index])
        title_words = normalize_title(entry["title"]).split()
        if not title_words:
            continue

        matches = sum(1 for word in title_words if word in page_text)
        score = matches / len(title_words)
        if score >= 0.70:
            validated.append(entry)

    return validated

def classify_section(title: str) -> str:
    normalized = normalize_title(title)
    if "prologue" in normalized:
        return "prologue"

    if "epilogue" in normalized:
        return "epilogue"

    if normalized.startswith("part "):
        return "part"

    return "chapter"

def is_excluded_section(title: str) -> bool:
    normalized = normalize_title(title)
    if normalized in config.EXCLUDED_SECTIONS:
        return True

    for prefix in config.EXCLUDED_SECTION_PREFIXES:
        if normalized.startswith(prefix):
            return True

    return False

def choose_narrative_sections(toc_entries, page_texts):
    sections = []
    for index, entry in enumerate(toc_entries):
        if entry.get("excluded") or is_excluded_section(entry["title"]):
            continue

        title = entry["title"]
        start_page = entry["page"]
        next_title = None
        end_page = len(page_texts)
        for future_entry in toc_entries[index + 1:]:
            next_title = future_entry["title"]
            end_page = max(start_page, future_entry["page"])
            break

        sections.append({"title": title, "start_page": start_page, "end_page": end_page, "next_title": next_title,})

    prologue_index = None
    for index, section in enumerate(sections):
        if classify_section(section["title"]) == "prologue":
            prologue_index = index
            break

    if prologue_index is not None and prologue_index != 0:
        prologue = sections.pop(prologue_index)
        sections.insert(0, prologue)

    return sections

def extract_section_text(page_texts, start_page, end_page, title, next_title, repeated_first, repeated_last):
    pages = [clean_page(p, repeated_first, repeated_last) for p in page_texts[start_page - 1:end_page]]
    combined = "\n".join(pages)
    start_pos = 0
    if title:
        pat_start = re.compile(rf"^\s*{re.escape(title)}\b[:.\s]*", re.MULTILINE | re.IGNORECASE)
        m_start = pat_start.search(combined)
        if m_start:
            start_pos = m_start.end()

    end_pos = len(combined)
    if next_title:
        pat_end = re.compile(rf"^\s*{re.escape(next_title)}\b[:.\s]*", re.MULTILINE | re.IGNORECASE)
        m_end = pat_end.search(combined, pos=start_pos)
        if m_end:
            end_pos = m_end.start()

    sliced = combined[start_pos:end_pos].strip()
    return clean_text(sliced)

def strip_leading_title(text: str, title: str) -> str:
    norm_title = re.escape(title.strip())
    match = re.match(rf"^(?:{norm_title}|chapter\s+[0-9ivxlcdm]+|[0-9ivxlcdm]+)[\s.:\-–—]*", text, re.IGNORECASE)
    if match:
        remainder = text[match.end():].strip()
        if len(remainder) >= config.MIN_TEXT_CHARS:
            return remainder
    
    return text

def detect_chapters_from_content(page_texts: list[str]) -> list[dict]:
    entries = []
    chapter_pattern = re.compile(r"^\s*(?:chapter\s+([0-9ivxlcdm]+|[a-z]+)|part\s+([0-9ivxlcdm]+|[a-z]+)|act\s+([0-9ivxlcdm]+)|prologue|epilogue|book\s+([0-9ivxlcdm]+))\b[:.\s]*(.*?)$", re.IGNORECASE,)
    roman_pattern = re.compile(r"^\s*([ivxlcdm]{1,8})\s*$", re.IGNORECASE)
    academic_pattern = re.compile(r"^\s*(?:(?:[0-9]{1,2}\.|\b[IVXLCDM]{1,6}\.)\s+([A-Z][A-Za-z0-9\s,\-–—]{2,50})|Abstract)\b[:.\s]*$", re.IGNORECASE,)
    for page_idx, page_text in enumerate(page_texts, start=1):
        lines = [line.strip() for line in page_text.splitlines() if line.strip()]
        if not lines:
            continue

        for line in lines:
            if chapter_pattern.match(line) or roman_pattern.match(line) or academic_pattern.match(line):
                clean_cand = " ".join(line.split())
                is_excl = is_excluded_section(clean_cand)
                entries.append({"title": clean_cand, "page": page_idx, "excluded": is_excl})

    if not entries or all(e.get("excluded") for e in entries):
        entries = []
        chunk_size = 15
        total_pages = len(page_texts)
        if total_pages <= chunk_size:
            entries.append({"title": "Main Content", "page": 1, "excluded": False})

        else:
            for page_num in range(1, total_pages + 1, chunk_size):
                part_num = (page_num // chunk_size) + 1
                entries.append({"title": f"Section {part_num}", "page": page_num, "excluded": False})

    return entries

def process_pdf(pdf_path: Path, force_ocr: bool = False, session_directory: Path | None = None, on_scanned_detected = None, on_ocr_progress = None,):
    pdf = fitz.open(pdf_path)
    try:
        title, author = get_metadata(pdf, pdf_path)
        page_texts = None
        if session_directory and not force_ocr:
            page_texts = load_scanned_page_texts_cache(session_directory)

        if page_texts is None:
            raw_page_texts = extract_all_page_text(pdf)
            total_chars = sum(len(p.strip()) for p in raw_page_texts)
            avg_chars = total_chars / max(1, len(pdf))
            is_scanned = force_ocr or total_chars == 0 or (len(pdf) > 0 and avg_chars < config.MIN_TEXT_CHARS)
            if is_scanned and config.ENABLE_OCR_FALLBACK:
                if on_scanned_detected:
                    reason = "Forced OCR" if force_ocr else "Scanned/Image-based document detected"
                    on_scanned_detected(len(pdf), reason)

                page_texts = []
                for page_idx, page in enumerate(pdf, start=1):
                    ocr_text = ocr_page(page)
                    page_texts.append(ocr_text)
                    if on_ocr_progress:
                        on_ocr_progress(page_idx, len(pdf))

                if session_directory:
                    save_scanned_page_texts_cache(session_directory, page_texts)

            else:
                page_texts = list(raw_page_texts)
                if config.ENABLE_OCR_FALLBACK:
                    hybrid_pages_found = False
                    for page_idx, page in enumerate(pdf):
                        if len(page_texts[page_idx].strip()) < config.MIN_TEXT_CHARS and len(page.get_images()) > 0:
                            ocr_text = ocr_page(page)
                            if len(ocr_text.strip()) >= config.MIN_TEXT_CHARS:
                                page_texts[page_idx] = ocr_text
                                hybrid_pages_found = True

                    if hybrid_pages_found and session_directory:
                        save_scanned_page_texts_cache(session_directory, page_texts)

        if author == "Unknown" and page_texts:
            first_lines = [l.strip() for l in page_texts[0].splitlines() if l.strip()]
            for line in first_lines[:8]:
                m = re.match(r"^(?:by|written by)\s+([A-Za-z\s.\-]{3,40})$", line, re.IGNORECASE)
                if m:
                    candidate = m.group(1).strip()
                    if len(candidate.split()) <= 4:
                        author = candidate
                        break

        repeated_first, repeated_last = detect_repeated_edge_text(page_texts)
        toc_entries = []
        if config.USE_PDF_TOC:
            toc_entries = get_top_level_toc(pdf)
            toc_entries = validate_toc_entries(toc_entries, page_texts)

        if not toc_entries:
            toc_entries = detect_chapters_from_content(page_texts)

        raw_sections = choose_narrative_sections(toc_entries, page_texts)
        sections = []
        for item in raw_sections:
            text = extract_section_text(page_texts=page_texts, start_page=item["start_page"], end_page=item["end_page"], title=item["title"], next_title=item.get("next_title"), repeated_first=repeated_first, repeated_last=repeated_last,)
            if not text or len(text.strip()) < config.MIN_TEXT_CHARS: continue

            cleaned_section_text = strip_leading_title(text, item["title"])
            sections.append(Section(title=item["title"], start_page=item["start_page"], end_page=item["end_page"], text=cleaned_section_text,))

        return title, author, sections

    finally: pdf.close()