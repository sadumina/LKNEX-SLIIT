## This folder manages the trusted organisational documents used as evidence.

Documents are ingested once (offline), chunked, embedded and stored. At runtime the retrieval module reads from this store.

### Pipeline:
1. **`ingestion.py`**: Reads PDF, DOCX and TXT files and attaches metadata (document id, version, date, allowed roles).
2. **`preprocessing.py`**: Cleans text and splits it into chunks with section ids.
3. **`embeddings.py`**: Converts chunks into vectors.
4. **`vector Store.py`**: Stores and searches the vectors in ChromaDB.
5. **`retrieval.py`**: Hybrid vector and keyword (BM25) search, filtered by user role, preferring the latest document version.
