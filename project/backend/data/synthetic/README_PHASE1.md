# AEGIS AI — Phase 1: Synthetic Organisational Knowledge Base

All organisations, policies, values, and identifiers in this collection are fictional. These are not real SLIIT or Team LKNEX policies.

## Contents
- `organisational_documents.json`: 50 records, five evidence-ready sections per document.
- `documents/`: 50 searchable PDF policies.
- `documents_txt/`: matching 50 UTF-8 plain-text documents.
- `document_index.csv`: compact index for analysis and ingestion.
- `schemas/organisational_documents.schema.json`: JSON Schema for the document manifest.
- `phase1_validation_report.json`: counts, duplicates, category distribution and deliberate version conflicts.

## Evidence linking and version control
`document_id` is the canonical key. Each section has a stable `section_id` and a PDF `page`. `source_reference` is a synthetic URI, not a live web link. Retrieval queries in Phase 3 should reference `document_id` and `section_id`, and fact-verification examples in Phase 4 should reference the same source sections. Use `document_status=ACTIVE` and `effective_date` to filter current policy by default. Five paired topics have explicit legacy versions; use these to test stale-document handling.

## Ingestion
Read the JSON manifest using `json.load`; index `sections[].text` as ChromaDB documents with metadata `document_id`, `section_id`, `page`, `document_version`, `document_status`, and `effective_date`. Alternatively use PDFs with PyMuPDF. Do not treat synthetic URI identifiers as external URLs.

## Splits
Phase 1 is a knowledge base, not a train/test split. In Phases 2–5, create development and held-out evaluation splits by scenario and policy topic where possible to avoid leakage.
