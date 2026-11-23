## This folder holds the comparison systems used for benchmarking.

Both baselines return the same output format as the multi-agent system so the comparison is fair.

### Files included:
1. **`single_agent.py`**: One LLM component performs claim extraction, evidence assessment and verification.
2. **`passthrough.py`**: The unverified LLM baseline. It releases the draft answer as it is.
