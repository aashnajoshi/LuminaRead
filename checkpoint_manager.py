import hashlib
import json
import os
from pathlib import Path
import shutil
import tempfile
from typing import Any
import config

def compute_book_fingerprint(pdf_path: Path, voice: str | None = None) -> str:
    stat = pdf_path.stat()
    active_voice = voice or config.VOICE
    raw = f"{pdf_path.resolve()}_{stat.st_size}_{stat.st_mtime_ns}_{active_voice}"
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:16]

def get_checkpoint_dir(pdf_path: Path, output_dir: Path | None = None) -> Path:
    if not config.ENABLE_CHECKPOINTS:
        return Path(tempfile.mkdtemp(prefix="audiobook_"))

    fingerprint = compute_book_fingerprint(pdf_path, config.VOICE)
    safe_name = "".join(c for c in pdf_path.stem if c.isalnum() or c in ("-", "_")).strip()[:30]
    if not safe_name:
        safe_name = "audiobook"

    if config.CHECKPOINT_DIRECTORY:
        base_dir = Path(config.CHECKPOINT_DIRECTORY)

    elif output_dir:
        base_dir = output_dir / ".audiobook_cache"

    else:
        base_dir = pdf_path.parent / ".audiobook_cache"

    checkpoint_dir = base_dir / f"{safe_name}_{fingerprint}"
    try:
        checkpoint_dir.mkdir(parents=True, exist_ok=True)
        test_file = checkpoint_dir / ".write_test"
        test_file.write_text("ok", encoding="utf-8")
        test_file.unlink()
        return checkpoint_dir

    except Exception:
        fallback_dir = Path(tempfile.gettempdir()) / "audiobook_cache" / f"{safe_name}_{fingerprint}"
        fallback_dir.mkdir(parents=True, exist_ok=True)
        return fallback_dir

def save_atomic_file(target_path: Path, data: bytes | str):
    tmp_path = target_path.with_suffix(f"{target_path.suffix}.tmp_{os.getpid()}")
    try:
        if isinstance(data, bytes):
            tmp_path.write_bytes(data)

        else:
            tmp_path.write_text(data, encoding="utf-8")

        os.replace(tmp_path, target_path)

    except Exception:
        tmp_path.unlink(missing_ok=True)
        raise

def cleanup_corrupted_chunk(audio_path: Path, metadata_path: Path):
    try:
        audio_path.unlink(missing_ok=True)

    except OSError:
        pass

    try:
        metadata_path.unlink(missing_ok=True)

    except OSError:
        pass

    for tmp in audio_path.parent.glob(f"{audio_path.stem}.*tmp*"):
        try:
            tmp.unlink(missing_ok=True)

        except OSError:
            pass

def validate_cached_chunk(audio_path: Path, metadata_path: Path, expected_text: str, voice: str | None = None,) -> dict | None:
    if not audio_path.exists() or not metadata_path.exists():
        return None

    expected_voice = voice or config.VOICE
    try:
        if audio_path.stat().st_size < 300:
            cleanup_corrupted_chunk(audio_path, metadata_path)
            return None

        content = metadata_path.read_text(encoding="utf-8")
        data = json.loads(content)
        if data.get("text", "").strip() != expected_text.strip():
            cleanup_corrupted_chunk(audio_path, metadata_path)
            return None

        if data.get("voice") != expected_voice:
            cleanup_corrupted_chunk(audio_path, metadata_path)
            return None

        if not isinstance(data.get("boundaries"), list):
            cleanup_corrupted_chunk(audio_path, metadata_path)
            return None

        return data

    except Exception:
        cleanup_corrupted_chunk(audio_path, metadata_path)
        return None

def save_chunk_atomically(audio_path: Path, audio_bytes: bytes, metadata: dict):
    meta_path = audio_path.with_suffix(".json")
    save_atomic_file(audio_path, audio_bytes)
    save_atomic_file(meta_path, json.dumps(metadata, ensure_ascii=False, indent=2))

def validate_section_checkpoint(section_dir: Path, section_number: int, expected_chunks_count: int) -> Any | None:
    section_audio = section_dir / f"section_{section_number:03d}.mp3"
    section_meta = section_dir / f"section_{section_number:03d}_meta.json"
    if not section_audio.exists() or not section_meta.exists():
        return None

    try:
        if section_audio.stat().st_size < 500:
            return None

        data = json.loads(section_meta.read_text(encoding="utf-8"))
        chunk_durs = data.get("chunk_durations_ms", [])
        if len(chunk_durs) != expected_chunks_count:
            return None

        duration_ms = data.get("duration_ms", 0)
        if duration_ms <= 0:
            return None

        from narrator import SectionAudioResult
        from text_processor import SubtitleCue
        subtitle_cues = [SubtitleCue(start_ms=c["start_ms"], end_ms=c["end_ms"], text=c["text"]) for c in data.get("subtitle_cues", [])]
        return SectionAudioResult(audio_path=section_audio, duration_ms=duration_ms, subtitle_cues=subtitle_cues, chunk_durations_ms=chunk_durs,)

    except Exception:
        return None

def save_section_checkpoint(section_dir: Path, section_number: int, result: Any):
    meta_path = section_dir / f"section_{section_number:03d}_meta.json"
    payload = {
        "section_number": section_number,
        "duration_ms": result.duration_ms,
        "chunk_durations_ms": result.chunk_durations_ms,
        "subtitle_cues": [{"start_ms": c.start_ms, "end_ms": c.end_ms, "text": c.text} for c in result.subtitle_cues],
    }
    save_atomic_file(meta_path, json.dumps(payload, ensure_ascii=False, indent=2))

def save_extracted_images_cache(checkpoint_dir: Path, images: list[Any]):
    cache_file = checkpoint_dir / "extracted_images.json"
    payload = [
        {
            "image_path": str(img.image_path.resolve()),
            "page_number": img.page_number,
            "y0": img.y0,
            "y1": img.y1,
            "width": img.width,
            "height": img.height,
            "ocr_text": img.ocr_text,
        }
        for img in images
    ]
    save_atomic_file(cache_file, json.dumps(payload, ensure_ascii=False, indent=2))

def load_extracted_images_cache(checkpoint_dir: Path) -> list[Any] | None:
    cache_file = checkpoint_dir / "extracted_images.json"
    if not cache_file.exists():
        return None

    try:
        data = json.loads(cache_file.read_text(encoding="utf-8"))
        from image_processor import ExtractedImage
        images = []
        for item in data:
            p = Path(item["image_path"])
            if not p.exists():
                return None

            images.append(
                ExtractedImage(
                    image_path=p,
                    page_number=item["page_number"],
                    y0=item["y0"],
                    y1=item["y1"],
                    width=item["width"],
                    height=item["height"],
                    ocr_text=item.get("ocr_text", ""),
                )
            )

        return images

    except Exception:
        return None

def count_resumed_progress(checkpoint_dir: Path, section_plan: list[tuple[Any, list[str]]]) -> tuple[int, int, int]:
    total_steps = sum(len(chunks) + 1 for _, chunks in section_plan)
    cached_sections = 0
    cached_steps = 0
    for sec_idx, (section, chunks) in enumerate(section_plan, start=1):
        sec_dir = checkpoint_dir / f"section_{sec_idx:03d}"
        if validate_section_checkpoint(sec_dir, sec_idx, len(chunks)) is not None:
            cached_sections += 1
            cached_steps += len(chunks) + 1

        else:
            heading_path = sec_dir / "heading.mp3"
            heading_meta = sec_dir / "heading.json"
            if validate_cached_chunk(heading_path, heading_meta, section.title) is not None:
                cached_steps += 1

            for chunk_idx, chunk_text in enumerate(chunks, start=1):
                c_path = sec_dir / f"chunk_{chunk_idx:04d}.mp3"
                m_path = sec_dir / f"chunk_{chunk_idx:04d}.json"
                if validate_cached_chunk(c_path, m_path, chunk_text) is not None:
                    cached_steps += 1

    return cached_sections, cached_steps, total_steps

def cleanup_intermediate_chunks(checkpoint_dir: Path, num_sections: int):
    if not config.CLEANUP_CHUNKS_ON_SUCCESS:
        return

    for sec_idx in range(1, num_sections + 1):
        sec_dir = checkpoint_dir / f"section_{sec_idx:03d}"
        if not sec_dir.exists():
            continue

        for item in sec_dir.iterdir():
            if item.name.startswith("chunk_") or item.name.startswith("heading."):
                try:
                    item.unlink(missing_ok=True)

                except OSError:
                    pass

def save_scanned_page_texts_cache(checkpoint_dir: Path | None, page_texts: list[str]) -> None:
    if not checkpoint_dir:
        return

    cache_file = checkpoint_dir / "scanned_page_texts.json"
    save_atomic_file(cache_file, json.dumps(page_texts, indent=2, ensure_ascii=False))

def load_scanned_page_texts_cache(checkpoint_dir: Path | None) -> list[str] | None:
    if not checkpoint_dir:
        return None

    cache_file = checkpoint_dir / "scanned_page_texts.json"
    if not cache_file.exists():
        return None

    try:
        with open(cache_file, "r", encoding="utf-8") as f:
            data = json.load(f)

        if isinstance(data, list) and len(data) > 0 and any(len(p.strip()) > 0 for p in data):
            return data

    except Exception: pass
    return None