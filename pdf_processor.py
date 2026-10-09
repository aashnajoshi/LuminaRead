from dataclasses import dataclass
from pathlib import Path
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

def process_pdf(pdf_path: Path):
    pdf = fitz.open(pdf_path)
    try:
        title, author = get_metadata(pdf, pdf_path,)
        page_texts = extract_all_page_text(pdf)
        repeated_first, repeated_last = (detect_repeated_edge_text(page_texts))
        if USE_PDF_TOC:
            toc_entries = get_top_level_toc(pdf)
            toc_entries = validate_toc_entries(toc_entries, page_texts,)

        else:
            toc_entries = []

        if not toc_entries:
            raise RuntimeError("No usable top-level PDF table of contents was found.")

        raw_sections = choose_narrative_sections(toc_entries, page_texts,)
        sections = []
        for item in raw_sections:
            text = extract_section_text(
                page_texts=page_texts,
                start_page=item["start_page"],
                end_page=item["end_page"],
                repeated_first=repeated_first,
                repeated_last=repeated_last,)

            if not text:
                continue

            sections.append(
                Section(
                    title=item["title"],
                    start_page=item["start_page"],
                    end_page=item["end_page"],
                    text=text,))

        return title, author, sections

    finally:
        pdf.close()