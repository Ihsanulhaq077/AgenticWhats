import re

_SENTENCE_SPLIT = re.compile(r"(?<=[.!?؟])\s+")


def _split_sentences(text: str) -> list[str]:
    parts = [s.strip() for s in _SENTENCE_SPLIT.split(text) if s.strip()]
    return parts or ([text.strip()] if text.strip() else [])


def chunk_text(text: str, max_chars: int = 700, overlap_sentences: int = 1) -> list[str]:
    """Sentence-aware sliding-window chunking.

    Keeps chunks under ``max_chars`` and carries ``overlap_sentences`` sentences
    between consecutive chunks so answers that span a boundary remain retrievable.
    FAQ-style documents (one "Q: ... A: ..." pair per paragraph) are kept whole
    whenever they fit.
    """
    paragraphs = [p.strip() for p in text.split("\n\n") if p.strip()]
    chunks: list[str] = []

    def flush(buf: list[str]) -> None:
        if buf:
            chunks.append("\n".join(buf).strip())

    for paragraph in paragraphs:
        if len(paragraph) <= max_chars:
            flush([paragraph])
            continue
        buf: list[str] = []
        size = 0
        for sentence in _split_sentences(paragraph):
            # A single oversized sentence is hard-split as a last resort.
            while len(sentence) > max_chars:
                flush(buf + [sentence[:max_chars]])
                sentence = sentence[max_chars:]
                buf, size = [], 0
            if size + len(sentence) + 1 > max_chars and buf:
                flush(buf)
                buf = buf[-overlap_sentences:] if overlap_sentences else []
                size = sum(len(s) + 1 for s in buf)
            buf.append(sentence)
            size += len(sentence) + 1
        flush(buf)
    return chunks
