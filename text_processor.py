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

def clean_academic_text(text: str) -> str:
    """Cleans academic citations, URLs, footnote markers, and LaTeX notation for natural TTS narration."""
    if not text:
        return ""

    # 1. Bracketed numerical citations: [1], [1, 2], [3-6], [12, 14, 20-22], [S1, S2]
    text = re.sub(r"\[\s*(?:[A-Za-z]?\d{1,4}(?:\s*[-–—]\s*[A-Za-z]?\d{1,4})?\s*[,;]?\s*)+\]", "", text)

    # 2. Parenthetical figure/table callouts: (see Figure 1a), (Fig. 2), (Table 3)
    text = re.sub(r"\(\s*(?:see\s+)?(?:figure|fig\.?|table)\s+[0-9a-z.\-]+\s*\)", "", text, flags=re.IGNORECASE)

    # Parenthetical URLs, DOIs, arXiv IDs: (available at https://...) or (doi: ...)
    text = re.sub(r"\(\s*(?:https?://\S+|doi:\s*10\.\S+|see\s+https?://\S+|available\s+at\s+https?://\S+)\s*\)", "", text, flags=re.IGNORECASE)

    # Author-year citations: (Smith et al., 2020), (Smith & Jones, 2019), (e.g., Wang, 2018; Li, 2021)
    author_year = r"(?:(?:see|e\.g\.|i\.e\.|cf\.|also)?\s*[A-Z][A-Za-zÀ-ÿ\-]+(?:\s+(?:et\s+al\.?|and|&)\s+[A-Z][A-Za-zÀ-ÿ\-]+)?(?:\s+et\s+al\.?)?,\s*(?:18|19|20)\d{2}[a-z]?(?:[;,]\s*(?:(?:see|e\.g\.|i\.e\.|cf\.|also)?\s*[A-Z][A-Za-zÀ-ÿ\-]+(?:\s+(?:et\s+al\.?|and|&)\s+[A-Z][A-Za-zÀ-ÿ\-]+)?(?:\s+et\s+al\.?)?,\s*)?(?:18|19|20)\d{2}[a-z]?)*)"
    text = re.sub(rf"\(\s*{author_year}\s*\)", "", text)

    # Textual year citations after author names: 'Vaswani et al. (2017)' -> 'Vaswani et al.'
    text = re.sub(r"(\b[A-Z][A-Za-zÀ-ÿ\-]+(?:\s+et\s+al\.?)?)\s*\((?:18|19|20)\d{2}[a-z]?\)", r"\1", text)

    # 3. Footnote numbers glued to word endings (e.g. 'architecture1.' -> 'architecture.')
    text = re.sub(r"\b([a-zA-Z]{3,})[1-9](?=[,.;:!?\s]|$)", r"\1", text)

    # 4. URLs & DOIs
    text = re.sub(r"\b(?:is\s+)?available\s+at\s+https?://\S+", "is available online", text, flags=re.IGNORECASE)
    text = re.sub(r"\bat\s+https?://\S+", "online", text, flags=re.IGNORECASE)
    text = re.sub(r"https?://\S+|www\.\S+", "", text)
    text = re.sub(r"\b(?:doi|DOI):\s*10\.\d{4,9}/[-._;()/:A-Za-z0-9]+", "", text)
    text = re.sub(r"\barXiv:\d{4}\.\d{4,5}(?:v\d+)?\b", "", text)

    # 5. LaTeX Math conversions
    latex_map = {
        r"\\alpha": "alpha", r"\\beta": "beta", r"\\gamma": "gamma", r"\\delta": "delta",
        r"\\epsilon": "epsilon", r"\\theta": "theta", r"\\lambda": "lambda", r"\\mu": "mu",
        r"\\pi": "pi", r"\\sigma": "sigma", r"\\phi": "phi", r"\\omega": "omega",
        r"\\sum": "sum", r"\\prod": "product", r"\\int": "integral", r"\\infty": "infinity",
        r"\\approx": "approximately", r"\\leq": "less than or equal to", r"\\geq": "greater than or equal to",
        r"\\neq": "not equal to", r"\\times": "times", r"\\pm": "plus or minus",
    }
    for cmd, spoken in latex_map.items():
        text = re.sub(rf"{cmd}\b", spoken, text)

    # Unpack LaTeX formatting wrappers: \mathbf{x} -> x, \mathcal{L} -> L, \text{hello} -> hello
    text = re.sub(r"\\[a-zA-Z]+\{([^{}]+)\}", r"\1", text)
    text = re.sub(r"\\[a-zA-Z]+", "", text)
    text = re.sub(r"[\$\^_{}]", " ", text)

    # 6. Punctuation cleanup
    text = re.sub(r"\(\s*\)", "", text)
    text = re.sub(r"\[\s*\]", "", text)
    text = re.sub(r"\s+([,.:;!?])", r"\1", text)
    text = re.sub(r"[,;]\s*([.:;!?])", r"\1", text)
    text = re.sub(r"\.{2,}", ".", text)
    text = " ".join(text.split())
    return text.strip()

def split_into_sentences(text: str) -> list[str]:
    text = text.strip()
    if not text:
        return []

    pattern = re.compile(r".+?(?:" r"(?<=[.!?])" r'["\'”’»)]*' r"(?=\s+|$)" r"|$" r")", re.DOTALL)
    sentences = [match.group(0).strip() for match in pattern.finditer(text) if match.group(0).strip()]
    return sentences or [text]

def split_long_text(text: str, max_chars: int = MAX_TTS_CHARS) -> list[str]:
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
                end = min(start + max_chars, len(word))
                chunks.append(word[start:end])
                start = end

            current = ""

        else:
            current = word

    if current:
        chunks.append(current)

    return chunks

def split_text_for_tts(text: str, max_chars: int = MAX_TTS_CHARS) -> list[str]:
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

            chunks.extend(split_long_text(sentence, max_chars))
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
        return NarrationCue(text=text, style="surprised", rate="-5%", pitch="+5Hz", volume="+0%")

    if "!!" in text:
        return NarrationCue(text=text, style="strong_emphasis", rate="+0%", pitch="+5Hz", volume="+5%")

    if "!" in text:
        return NarrationCue(text=text, style="emphatic", rate="+0%", pitch="+3Hz", volume="+3%")

    if "..." in text:
        return NarrationCue(text=text, style="reflective", rate="-8%", pitch="-2Hz", volume="-2%")

    return NarrationCue(text=text, style="neutral", rate=SPEECH_RATE, pitch=SPEECH_PITCH, volume=SPEECH_VOLUME)

def create_heading_cue(title: str) -> NarrationCue:
    return NarrationCue(text=title, style="chapter_heading", rate="+0%", pitch="+0Hz", volume="+0%", pause_after_ms=600)

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

        matched_words.append({"start_ms": start_ms, "end_ms": end_ms, "text": chosen_token})

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
            if len(combined_text) <= (max_chars + 12) and (current_chunk[0]["end_ms"] - prev.start_ms) <= (max_duration_ms + 1000):
                prev.text = combined_text
                prev.end_ms = current_chunk[0]["end_ms"]
                current_chunk.clear()
                return

        cue_text = " ".join(item["text"] for item in current_chunk).strip()
        if cue_text:
            cues.append(SubtitleCue(start_ms=current_chunk[0]["start_ms"], end_ms=current_chunk[-1]["end_ms"], text=cue_text))

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
        if has_terminal_break or has_quote_break: flush()

        elif has_clause_break and (len(current_chunk) >= 3 or cur_dur >= 1500 or is_too_long): flush()

        elif is_too_long: flush()

    flush()
    return cues