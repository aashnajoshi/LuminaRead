from dataclasses import dataclass
from pathlib import Path
import re
import pymupdf as fitz
from config import (
    EXCLUDED_SECTION_PREFIXES,
    EXCLUDED_SECTIONS,
    IGNORED_TEXT,
    MIN_TEXT_CHARS,
    USE_PDF_TOC,
    VALIDATE_TOC,
)

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
    for ignored in IGNORED_TEXT:
        text = text.replace(ignored, "")

    text = text.replace("-\n", "")
    text = text.replace("\r\n", "\n")
    text = text.replace("\r", "\n")
    text = text.replace("\n", " ")
    text = " ".join(text.split())
    return text.strip()

def get_metadata(pdf, pdf_path: Path):
    metadata = pdf.metadata or {}
    title = metadata.get("title") or pdf_path.stem
    author = metadata.get("author") or "Unknown"
    title = title.strip() or pdf_path.stem
    author = author.strip() or "Unknown"
    return title, author

def extract_page_text(page) -> str:
    return page.get_text("text") or ""

def extract_all_page_text(pdf) -> list[str]:
    return [extract_page_text(page) for page in pdf]

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

def remove_repeated_edge_lines(text: str, repeated_first: set[str], repeated_last: set[str],) -> str:
    lines = [line for line in text.splitlines() if line.strip()]
    if not lines:
        return ""

    if normalize_title(lines[0]) in repeated_first:
        lines = lines[1:]

    if lines and normalize_title(lines[-1]) in repeated_last:
        lines = lines[:-1]

    return "\n".join(lines)

def clean_page(text: str, repeated_first: set[str], repeated_last: set[str],) -> str:
    text = remove_page_numbers(text)
    text = remove_repeated_edge_lines(text, repeated_first, repeated_last,)
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

        entries.append({"title": title.strip(), "page": max(1, page),})

    return entries

def validate_toc_entries(toc_entries, page_texts):
    if not VALIDATE_TOC:
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
    if normalized in EXCLUDED_SECTIONS:
        return True

    for prefix in EXCLUDED_SECTION_PREFIXES:
        if normalized.startswith(prefix):
            return True

    return False

def choose_narrative_sections(toc_entries, page_texts):
    sections = []
    for index, entry in enumerate(toc_entries):
        title = entry["title"]
        start_page = entry["page"]
        if index + 1 < len(toc_entries):
            end_page = toc_entries[index + 1]["page"] - 1

        else:
            end_page = len(page_texts)

        if start_page > end_page:
            continue

        if is_excluded_section(title):
            continue

        sections.append({"title": title, "start_page": start_page, "end_page": end_page,})

    prologue_index = None
    for index, section in enumerate(sections):
        if classify_section(section["title"]) == "prologue":
            prologue_index = index
            break

    if prologue_index is not None and prologue_index != 0:
        prologue = sections.pop(prologue_index)
        sections.insert(0, prologue)

    return sections

def extract_section_text(page_texts, start_page, end_page, repeated_first, repeated_last,):
    pages = page_texts[start_page - 1:end_page]
    cleaned_pages = []
    for page in pages:
        cleaned_page = clean_page(page, repeated_first, repeated_last,)
        if len(cleaned_page.strip()) >= MIN_TEXT_CHARS:
            cleaned_pages.append(cleaned_page)

    return clean_text("\n".join(cleaned_pages))

def strip_leading_title(text: str, title: str) -> str:
    #  Prevents duplicate spoken narration if the page text begins with the chapter title or numeral (e.g. 'I', 'Chapter 1').
    norm_title = re.escape(title.strip())
    match = re.match(rf"^(?:{norm_title}|chapter\s+[0-9ivxlcdm]+|[0-9ivxlcdm]+)[\s.:\-–—]*", text, re.IGNORECASE,)
    if match:
        remainder = text[match.end():].strip()
        if len(remainder) >= MIN_TEXT_CHARS:
            return remainder
    
    return text

def detect_chapters_from_content(page_texts: list[str]) -> list[dict]:
    # Intelligent heuristic detection for chapters using page text patterns, whitespace isolation, and common book headings (Chapter, Act, Part, Roman Numerals).
    entries = []
    chapter_pattern = re.compile(r"^\s*(?:chapter\s+([0-9ivxlcdm]+|[a-z]+)|part\s+([0-9ivxlcdm]+|[a-z]+)|act\s+([0-9ivxlcdm]+)|prologue|epilogue|book\s+([0-9ivxlcdm]+))\b[:.\s]*(.*?)$", re.IGNORECASE,)
    roman_pattern = re.compile(r"^\s*([ivxlcdm]{1,8})\s*$", re.IGNORECASE)
    for page_idx, page_text in enumerate(page_texts, start=1):
        lines = [line.strip() for line in page_text.splitlines() if line.strip()]
        if not lines:
            continue

        header_candidate = None
        for line in lines[:3]:
            if chapter_pattern.match(line) or roman_pattern.match(line):
                header_candidate = line
                break

        if header_candidate:
            clean_cand = " ".join(header_candidate.split())
            if not is_excluded_section(clean_cand):
                entries.append({"title": clean_cand, "page": page_idx})

    # If no chapters detected, group pages into logical segments
    if not entries:
        chunk_size = 15
        total_pages = len(page_texts)
        if total_pages <= chunk_size:
            entries.append({"title": "Main Content", "page": 1})
        
        else:
            for page_num in range(1, total_pages + 1, chunk_size):
                part_num = (page_num // chunk_size) + 1
                entries.append({"title": f"Section {part_num}", "page": page_num})

    return entries

def process_pdf(pdf_path: Path):
    pdf = fitz.open(pdf_path)
    try:
        title, author = get_metadata(pdf, pdf_path)
        page_texts = extract_all_page_text(pdf)
        repeated_first, repeated_last = detect_repeated_edge_text(page_texts)
        toc_entries = []
        if USE_PDF_TOC:
            toc_entries = get_top_level_toc(pdf)
            toc_entries = validate_toc_entries(toc_entries, page_texts)

        # Intelligent fallback if no usable TOC found in PDF
        if not toc_entries:
            toc_entries = detect_chapters_from_content(page_texts)

        raw_sections = choose_narrative_sections(toc_entries, page_texts)
        sections = []
        for item in raw_sections:
            text = extract_section_text(page_texts=page_texts, start_page=item["start_page"], end_page=item["end_page"], repeated_first=repeated_first, repeated_last=repeated_last,)
            if not text:
                continue

            # Strip leading title or numeral duplication from narrative text
            cleaned_section_text = strip_leading_title(text, item["title"])
            sections.append(Section(title=item["title"], start_page=item["start_page"], end_page=item["end_page"], text=cleaned_section_text,))

        return title, author, sections

    finally: pdf.close()