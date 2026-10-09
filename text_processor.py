from dataclasses import dataclass
import re

from config import (
    MAX_TTS_CHARS,
    SPEECH_PITCH,
    SPEECH_RATE,
    SPEECH_VOLUME,
)

@dataclass
class NarrationCue:
    text: str
    style: str = "neutral"
    rate: str | None = None
    pitch: str | None = None
    volume: str | None = None
    pause_before_ms: int = 0
    pause_after_ms: int = 0

def split_into_sentences(text: str) -> list[str]:
    text = text.strip()
    if not text:
        return []

    pattern = re.compile(r".+?(?:" r"(?<=[.!?])" r'["\'”’»)]*' r"(?=\s+|$)" r"|$" r")", re.DOTALL,)
    sentences = [match.group(0).strip() for match in pattern.finditer(text) if match.group(0).strip()]
    return sentences or [text]

def split_long_text(text: str, max_chars: int = MAX_TTS_CHARS,) -> list[str]:
    text = text.strip()
    if len(text) <= max_chars:
        return [text]

    words = text.split()
    chunks = []
    current = ""
    for word in words:
        proposed = (word if not current else f"{current} {word}")
        if len(proposed) <= max_chars:
            current = proposed
            continue

        if current:
            chunks.append(current)

        if len(word) > max_chars:
            start = 0

            while start < len(word):
                end = min(start + max_chars, len(word),)
                chunks.append(word[start:end])
                start = end

            current = ""

        else:
            current = word

    if current:
        chunks.append(current)

    return chunks

def split_text_for_tts(text: str, max_chars: int = MAX_TTS_CHARS,) -> list[str]:
    text = text.strip()
    if not text:
        return []

    sentences = split_into_sentences(text)
    chunks = []
    current = ""
    for sentence in sentences:
        if len(sentence) > max_chars:
            if current:
                chunks.append(current)
                current = ""

            chunks.extend(split_long_text(sentence, max_chars,))
            continue

        proposed = (sentence if not current else f"{current} {sentence}")
        if len(proposed) <= max_chars:
            current = proposed

        else:
            if current:
                chunks.append(current)

            current = sentence

    if current:
        chunks.append(current)

    return chunks

def interpret_text(text: str) -> NarrationCue:
    text = text.strip()
    if not text:
        return NarrationCue(text="")

    if "?!" in text or "!?" in text:
        return NarrationCue(
            text=text,
            style="surprised",
            rate="-5%",
            pitch="+5Hz",
            volume="+0%",)

    if "!!" in text:
        return NarrationCue(
            text=text,
            style="strong_emphasis",
            rate="+0%",
            pitch="+5Hz",
            volume="+5%",)

    if "!" in text:
        return NarrationCue(
            text=text,
            style="emphatic",
            rate="+0%",
            pitch="+3Hz",
            volume="+3%",)

    if "..." in text:
        return NarrationCue(
            text=text,
            style="reflective",
            rate="-8%",
            pitch="-2Hz",
            volume="-2%",)

    return NarrationCue(
        text=text,
        style="neutral",
        rate=SPEECH_RATE,
        pitch=SPEECH_PITCH,
        volume=SPEECH_VOLUME,)

def create_heading_cue(title: str) -> NarrationCue:
    return NarrationCue(
        text=title,
        style="chapter_heading",
        rate="+0%",
        pitch="+0Hz",
        volume="+0%",
        pause_after_ms=600,)