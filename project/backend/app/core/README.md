## This folder holds shared infrastructure used by every other module.

### Files included:
1. **config.py**: Loads settings and environment variables.
2. **llm_client.py**: The only place that calls the LLM. Handles timeouts, retries, JSON parsing and token and cost counting.
3. **tracing.py**: Records every agent step so decisions can be audited.
4. **security.py**: Deterministic security controls (role-based access filtering, injection patterns, sensitive-data masking).

Never commit API keys. Secrets are read from environment variables only.
