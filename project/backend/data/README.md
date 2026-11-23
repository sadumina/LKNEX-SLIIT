## This folder holds all sample data, benchmark data and generated files.

JSON and JSONL files cannot contain comments, so each file's purpose is listed here.

### Contents:
1. **`sample_documents/`**: The trusted sample document collection used as evidence.
   - `manifest.json`: Lists every document with its id, version, effective date, allowed roles and current or superseded status.
2. **`benchmark/`**: Labelled test data used by the evaluation.
   - `claims_labelled.jsonl`: Claims labelled as supported, contradicted or unsupported, with the correct evidence.
   - `injection_cases.jsonl`: Documents containing malicious instructions, used to test security detection.
   - `permission_cases.jsonl`: Cases where evidence is restricted to certain roles, used to test access control.
3. **`processed/`**: Generated chunks and indexes. Created by the ingestion step, do not edit by hand.
4. **`users.json`**: Demo users and their roles.

Never place real confidential documents or secrets in this folder.
