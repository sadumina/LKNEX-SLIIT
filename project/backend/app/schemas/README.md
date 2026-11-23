## This folder defines the data contracts shared by the whole system.

All models are Pydantic classes. Every agent, service and API route uses these same models, so changes here affect everyone. Agree on them early and change them only through the folder owner.

### Files included:
1. **`verification.py`**: Models for claims, evidence, verdicts and security reports.
2. **`decision.py`**: Models for the policy decision and the final verification result.
3. **`api.py`**: Request and response models for the API routes.
