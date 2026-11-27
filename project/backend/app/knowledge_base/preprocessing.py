# Purpose of this file is to clean document text and split it into chunks with section references

"""Step 2 of the knowledge-base pipeline: page records -> clean chunks.

What happens here
-----------------
1. Clean the text (ligatures, hyphenated line breaks, stray whitespace).
2. Remove running headers/footers and page numbers that repeat on every page.
3. Detect numbered sections ("2.1 Return window") so every chunk knows its section.
4. Cut the text into chunks. A chunk never crosses a page (keeps the page number
   correct) and never mixes two numbered sections (keeps evidence precise).
"""
import json
import math
import re
import unicodedata
from collections import Counter
from pathlib import Path
from typing import Iterable

from pydantic import BaseModel

from app.knowledge_base.ingestion import PageRecord

MAX_WORDS = 180          # target upper size of a chunk
OVERLAP_SENTENCES = 1    # sentences repeated between two chunks cut from one long paragraph
MIN_WORDS = 3            # chunks shorter than this are noise and are dropped
HEADING_MAX_WORDS = 10   # a short line without a final period is treated as a heading

# "2.1 Text" or "2. Text" or "2) Text". Plain "14 days ..." must NOT match.
SECTION_RE = re.compile(r"^(\d+(?:\.\d+)+|\d+[.)])\s+(?=[A-Za-z])")
PAGE_NUMBER_RE = re.compile(r"^(?:page\s*)?\d+(?:\s*(?:of|/)\s*\d+)?$", re.IGNORECASE)


class Chunk(BaseModel):
    """A passage of a document that can be retrieved as evidence."""

    chunk_id: str
    doc_id: str
    doc_title: str
    version: str
    effective_date: str | None = None
    status: str
    page: int
    section: str | None = None
    text: str

    @property
    def index_text(self) -> str:
        """Text used for search. The title is added so queries naming the document match."""
        return f"{self.doc_title} v{self.version}. {self.text}"


# Cleaning
def clean_text(text: str) -> str:
    """Normalise one page of raw extracted text. Line breaks are kept."""
    text = unicodedata.normalize("NFKC", text)           # ligatures, non-breaking spaces
    text = text.replace("\u00ad", "")                    # soft hyphens
    text = re.sub(r"(\w)-\n(\w)", r"\1\2", text)         # "refund-\nable" -> "refundable"
    lines = [re.sub(r"[ \t]+", " ", line).strip() for line in text.split("\n")]
    text = "\n".join(lines)
    return re.sub(r"\n{3,}", "\n\n", text).strip()


def _line_key(line: str) -> str:
    """Digits are masked so "Page 1 of 3" and "Page 2 of 3" count as the same line."""
    return re.sub(r"\d+", "#", line.strip().lower())


def strip_repeated_lines(pages: list[PageRecord]) -> list[PageRecord]:
    """Remove running headers/footers and page numbers from the pages of ONE document."""
    n = len(pages)
    repeated: set[str] = set()
    if n >= 2:
        counts: Counter[str] = Counter()
        for page in pages:
            counts.update({_line_key(l) for l in page.text.split("\n") if l.strip()})
        threshold = max(2, math.ceil(0.6 * n))
        repeated = {key for key, count in counts.items() if count >= threshold}

    cleaned: list[PageRecord] = []
    for page in pages:
        kept = []
        for line in page.text.split("\n"):
            stripped = line.strip()
            if stripped and (_line_key(stripped) in repeated or PAGE_NUMBER_RE.match(stripped)):
                continue
            kept.append(line)
        text = re.sub(r"\n{3,}", "\n\n", "\n".join(kept)).strip()
        if text:
            cleaned.append(PageRecord(doc=page.doc, page=page.page, text=text))
    return cleaned


# Sections and blocks
def _iter_blocks(text: str, section: str | None) -> tuple[list[tuple[str | None, str]], str | None]:
    """Split a page into (section, text) blocks.

    A blank line ends a paragraph; a line starting with a section number starts a
    new block. ``section`` is carried over from the previous page so a clause that
    continues on the next page keeps its section id.
    """
    blocks: list[tuple[str | None, str]] = []
    lines: list[str] = []
    block_section = section

    def flush() -> None:
        nonlocal lines
        if lines:
            blocks.append((block_section, " ".join(lines)))
            lines = []

    for paragraph in re.split(r"\n\s*\n", text):
        flush()
        for line in paragraph.split("\n"):
            line = line.strip()
            if not line:
                continue
            match = SECTION_RE.match(line)
            if match:
                flush()
                section = match.group(1).rstrip(".)")
            if not lines:
                block_section = section
            lines.append(line)
    flush()
    return blocks, section


def _is_heading(text: str) -> bool:
    """A numbered, short line without final punctuation, e.g. "2. Online order returns"."""
    return (
        bool(SECTION_RE.match(text))
        and len(text.split()) <= HEADING_MAX_WORDS
        and not text.rstrip().endswith((".", "!", "?", ":"))
    )


def _attach_headings(blocks: list[tuple[str | None, str]]) -> list[tuple[str | None, str]]:
    """Merge a heading-only block ("2. Online order returns") into the block after it."""
    result: list[tuple[str | None, str]] = []
    pending: str | None = None
    for section, text in blocks:
        if _is_heading(text):
            pending = f"{pending} {text}" if pending else text
            continue
        if pending:
            text, pending = f"{pending} {text}", None
        result.append((section, text))
    if pending:                                  # heading at the very end of a page
        result.append((blocks[-1][0], pending))
    return result


# Chunking
def _split_long(text: str, max_words: int = MAX_WORDS, overlap: int = OVERLAP_SENTENCES) -> list[str]:
    """Cut a long paragraph at sentence boundaries, repeating ``overlap`` sentences."""
    if len(text.split()) <= max_words:
        return [text]
    sentences = re.split(r"(?<=[.!?])\s+", text)
    pieces: list[str] = []
    current: list[str] = []
    current_words = 0
    for sentence in sentences:
        words = len(sentence.split())
        if current and current_words + words > max_words:
            pieces.append(" ".join(current))
            current = current[-overlap:] if overlap else []
            current_words = sum(len(s.split()) for s in current)
        current.append(sentence)
        current_words += words
    if current:
        pieces.append(" ".join(current))
    return pieces


def _merge_small_blocks(blocks: list[tuple[str | None, str]]) -> list[tuple[str | None, str]]:
    """Join consecutive blocks of the same section while they stay under MAX_WORDS."""
    merged: list[tuple[str | None, str]] = []
    for section, text in blocks:
        if merged and merged[-1][0] == section and len(merged[-1][1].split()) + len(text.split()) <= MAX_WORDS:
            merged[-1] = (section, f"{merged[-1][1]} {text}")
        else:
            merged.append((section, text))
    return merged


def chunk_document(pages: list[PageRecord]) -> list[Chunk]:
    """Turn the (already cleaned) pages of one document into chunks."""
    chunks: list[Chunk] = []
    section: str | None = None
    for page in pages:
        blocks, section = _iter_blocks(page.text, section)
        blocks = _merge_small_blocks(_attach_headings(blocks))
        index = 0
        for block_section, block_text in blocks:
            for piece in _split_long(block_text):
                if len(piece.split()) < MIN_WORDS:
                    continue
                index += 1
                doc = page.doc
                chunks.append(
                    Chunk(
                        chunk_id=f"{doc.doc_id}:v{doc.version}:p{page.page}:{index}",
                        doc_id=doc.doc_id,
                        doc_title=doc.title,
                        version=doc.version,
                        effective_date=doc.effective_date,
                        status=doc.status,
                        page=page.page,
                        section=block_section,
                        text=piece,
                    )
                )
    return chunks


def build_chunks(pages: Iterable[PageRecord]) -> list[Chunk]:
    """Clean and chunk the pages of all documents."""
    by_doc: dict[str, list[PageRecord]] = {}
    for page in pages:
        by_doc.setdefault(page.doc.doc_id, []).append(
            PageRecord(doc=page.doc, page=page.page, text=clean_text(page.text))
        )

    chunks: list[Chunk] = []
    for doc_pages in by_doc.values():
        chunks.extend(chunk_document(strip_repeated_lines(doc_pages)))
    return chunks


# Persistence
def save_chunks(chunks: list[Chunk], path: Path | str) -> None:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps([c.model_dump() for c in chunks], indent=2, ensure_ascii=False), encoding="utf-8")


def load_chunks(path: Path | str) -> list[Chunk]:
    path = Path(path)
    if not path.exists():
        raise FileNotFoundError(f"{path} not found. Build the index first: python scripts/build_index.py")
    return [Chunk.model_validate(item) for item in json.loads(path.read_text(encoding="utf-8"))]
