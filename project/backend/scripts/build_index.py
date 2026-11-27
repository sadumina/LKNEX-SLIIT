# Purpose of this file is to run the offline knowledge-base pipeline once: PDFs -> chunks -> embeddings -> ChromaDB
"""Build (or rebuild) the search index.

Run from the backend folder:

    python scripts/build_index.py              # real embedding model (downloads it the first time)
    python scripts/build_index.py --offline    # fake embedder, no download (for quick checks only)
"""

import argparse
import logging
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.core.fakes import HashingEmbedder  # noqa: E402
from app.knowledge_base.retrieval import build_index  # noqa: E402


def main() -> None:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument(
        "--offline",
        action="store_true",
        help="use the fake embedder instead of the real model",
    )
    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    count = build_index(embedder=HashingEmbedder() if args.offline else None)
    print(f"Indexed {count} chunks.")


if __name__ == "__main__":
    main()
