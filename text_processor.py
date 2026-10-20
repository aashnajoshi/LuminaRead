from dataclasses import dataclass
import re
from config import (
    MAX_SUBTITLE_CHARS,
    MAX_SUBTITLE_DURATION_MS,
    MAX_SUBTITLE_WORDS,
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

@dataclass
class SubtitleCue:
    start_ms: int
    end_ms: int
    text: str

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
        return NarrationCue(text=text, style="surprised", rate="-5%", pitch="+5Hz", volume="+0%",)

    if "!!" in text:
        return NarrationCue(text=text, style="strong_emphasis", rate="+0%", pitch="+5Hz", volume="+5%",)

    if "!" in text:
        return NarrationCue(text=text, style="emphatic", rate="+0%", pitch="+3Hz", volume="+3%",)

    if "..." in text:
        return NarrationCue(text=text, style="reflective", rate="-8%", pitch="-2Hz", volume="-2%",)

    return NarrationCue(text=text, style="neutral", rate=SPEECH_RATE, pitch=SPEECH_PITCH, volume=SPEECH_VOLUME,)

def create_heading_cue(title: str) -> NarrationCue:
    return NarrationCue(text=title, style="chapter_heading", rate="+0%", pitch="+0Hz", volume="+0%", pause_after_ms=600,)

def group_words_into_subtitle_cues(original_text: str, word_events: list[dict], max_words: int = MAX_SUBTITLE_WORDS, max_chars: int = MAX_SUBTITLE_CHARS, max_duration_ms: int = MAX_SUBTITLE_DURATION_MS,) -> list[SubtitleCue]:
    """
    Groups word-level TTS timing events into natural, dialogue-synchronized subtitle cues:
    - Aligns word events with the original text to preserve quotes, casing, and punctuation.
    - Isolates spoken dialogue from attribution tags (e.g. '"What happened?"' vs 'he thought.').
    - Breaks naturally on clause boundaries (semicolons, colons, commas, dashes).
    - Enforces max word count, character count, and duration constraints.
    """
    if not word_events:
        return []

    pattern = re.compile(r"\S+")
    orig_tokens = [m.group(0) for m in pattern.finditer(original_text)]
    matched_words = []
    orig_idx = 0
    for event in word_events:
        event_text = event.get("text", "").strip()
        if not event_text:
            continue

        start_ms = round(event["offset_ms"])
        end_ms = round(event["offset_ms"] + event["duration_ms"])
        clean_event = re.sub(r"[^\w]", "", event_text.lower())
        chosen_token = event_text
        while orig_idx < len(orig_tokens):
            candidate = orig_tokens[orig_idx]
            clean_cand = re.sub(r"[^\w]", "", candidate.lower())
            if clean_event and (clean_event in clean_cand or clean_cand in clean_event):
                chosen_token = candidate
                orig_idx += 1
                break

            orig_idx += 1

        matched_words.append({"start_ms": start_ms, "end_ms": end_ms, "text": chosen_token,})

    if not matched_words:
        return []

    cues: list[SubtitleCue] = []
    current_chunk: list[dict] = []
    def flush(force: bool = False):
        if not current_chunk:
            return
        
        if len(current_chunk) == 1 and cues and not force:
            prev = cues[-1]
            combined_text = f"{prev.text} {current_chunk[0]['text']}"
            if (len(combined_text) <= (max_chars + 12) and (current_chunk[0]["end_ms"] - prev.start_ms) <= (max_duration_ms + 1000)):
                prev.text = combined_text
                prev.end_ms = current_chunk[0]["end_ms"]
                current_chunk.clear()
                return

        cue_text = " ".join(item["text"] for item in current_chunk).strip()
        if cue_text:
            cues.append(SubtitleCue(start_ms=current_chunk[0]["start_ms"], end_ms=current_chunk[-1]["end_ms"], text=cue_text,))

        current_chunk.clear()

    for item in matched_words:
        current_chunk.append(item)
        cur_text = " ".join(x["text"] for x in current_chunk)
        cur_dur = current_chunk[-1]["end_ms"] - current_chunk[0]["start_ms"]
        w_text = item["text"]
        has_quote_break = bool(re.search(r'["\'”’»]$', w_text))
        has_terminal_break = bool(re.search(r'[.!?]["\'”’»]?$', w_text))
        has_clause_break = bool(re.search(r'[,;:\-—–]["\'”’»]?$', w_text))
        is_too_long = (len(cur_text) >= max_chars or len(current_chunk) >= max_words or cur_dur >= max_duration_ms)
        if has_terminal_break or has_quote_break:
            flush()
        
        elif has_clause_break and (len(current_chunk) >= 3 or cur_dur >= 1500 or is_too_long):
            flush()
        
        elif is_too_long:
            flush()

    flush()
    return cues