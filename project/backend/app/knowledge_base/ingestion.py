# Purpose of this file is to read organisational documents and attach metadata such as version, date and allowed roles

"""Step 1 of the knowledge-base pipeline: PDF -> page records.

Document metadata (id, version, status, who may read it) comes from
``manifest.json``, never from the PDF text. This keeps versioning and access
control reliable and under the team's control.

Each page becomes one ``PageRecord`` so that page numbers survive all the way
to the final citation.
"""

import json
import logging
from dataclasses import dataclass
from pathlib import Path
from typing import Iterator, Literal

from pydantic import BaseModel, Field

try: 
    import pymupdf
except ImportError:  
    import fitz as pymupdf

logger = logging.getLogger(__name__)


class DocumentMeta(BaseModel):
    """One entry of manifest.json."""

    doc_id: str
    title: str
    version: str
    effective_date: str | None = None
    status: Literal["current", "superseded"] = "current"
    allowed_roles: list[str] = Field(default_factory=list)  
    filename: str

    def is_allowed(self, role: str | None) -> bool:
        """Default-deny: a missing or unknown role gets no documents."""
        if not role:
            return False
        return "*" in self.allowed_roles or role in self.allowed_roles


@dataclass
class PageRecord:
    """Raw text of one page plus the metadata of its document."""

    doc: DocumentMeta
    page: int  # 1-based
    text: str


def load_manifest(manifest_path: Path | str) -> list[DocumentMeta]:
    """Read and validate manifest.json."""
    path = Path(manifest_path)
    if not path.exists():
        raise FileNotFoundError(f"Manifest not found: {path}")
    data = json.loads(path.read_text(encoding="utf-8"))
    return [DocumentMeta.model_validate(item) for item in data["documents"]]


def iter_pages(
    manifest: list[DocumentMeta], docs_dir: Path | str
) -> Iterator[PageRecord]:
    """Yield one ``PageRecord`` per non-empty page of every document in the manifest."""
    docs_dir = Path(docs_dir)
    for doc in manifest:
        pdf_path = docs_dir / doc.filename
        if not pdf_path.exists():
            raise FileNotFoundError(
                f"{doc.doc_id}: file listed in manifest not found: {pdf_path}"
            )

        with pymupdf.open(pdf_path) as pdf:
            for page in pdf:
                # "blocks" keeps paragraph boundaries; sort=True gives reading order.
                blocks = page.get_text("blocks", sort=True)
                texts = [
                    b[4].strip() for b in blocks if b[6] == 0 and b[4].strip()
                ]  # b[6] == 0: text block
                text = "\n\n".join(texts)
                if not text.strip():
                    # Scanned pages have no text layer. OCR is out of scope for the MVP.
                    logger.warning(
                        "%s page %d has no extractable text (scanned?). Skipped.",
                        doc.doc_id,
                        page.number + 1,
                    )
                    continue
                yield PageRecord(doc=doc, page=page.number + 1, text=text)
