## This folder holds automated tests.

Tests use a fake LLM so they run without API cost and give repeatable results.

### Files included:
1. **`conftest.py`**: Shared test setup, including the fake LLM.
2. **`test_workflow.py`**: End-to-end test of the full verification workflow.
3. **`test_agents/`**: this folder is for One test file per agent.
