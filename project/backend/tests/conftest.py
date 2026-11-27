# Purpose of this file is to provide shared test fixtures, including a fake LLM and fake embedder that avoid real API calls and model downloads
import importlib.util
from pathlib import Path

import pytest

from app.core.fakes import HashingEmbedder
from app.knowledge_base.retrieval import DOCS_DIR, MANIFEST_PATH, build_index, load_retriever

BACKEND_DIR = Path(__file__).resolve().parents[1]


@pytest.fixture(scope="session")
def sample_docs():
    """Make sure the sample PDFs exist (generate them if they were not copied)."""
    if not (DOCS_DIR / "returns_policy_v3.2.pdf").exists():
        spec = importlib.util.spec_from_file_location("make_sample_docs", BACKEND_DIR / "scripts" / "make_sample_docs.py")
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        module.main()
    return DOCS_DIR


@pytest.fixture(scope="session")
def retriever(sample_docs, tmp_path_factory):
    """A real hybrid retriever (real PyMuPDF, ChromaDB, BM25) with the fake embedder, in a temp folder."""
    tmp = tmp_path_factory.mktemp("index")
    embedder = HashingEmbedder()
    build_index(
        docs_dir=sample_docs,
        manifest_path=MANIFEST_PATH,
        chunks_path=tmp / "chunks.json",
        store_path=tmp / "chroma",
        embedder=embedder,
    )
    return load_retriever(
        manifest_path=MANIFEST_PATH,
        chunks_path=tmp / "chunks.json",
        store_path=tmp / "chroma",
        embedder=embedder,
    )
