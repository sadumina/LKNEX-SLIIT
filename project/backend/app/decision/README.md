## This folder decides what happens to an AI answer after verification.

These are deterministic components, not LLM agents. Final decisions are enforced by rules so they cannot be bypassed by a model.

### Files included:
1. **Policy Engine**: Combines claim verdicts, security results and topic risk, then selects approve, correct, block or human review.
2. **Correction**: Rewrites the answer using verified claims only and attaches source citations.
