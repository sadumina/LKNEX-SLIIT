## This folder holds the services that connect the API to the workflow.

Both the API routes and the benchmark runner call these services, so they behave identically in the demo and in evaluation.

### Files included:
1. **verification_service.py**: Runs the full verification workflow for one answer.
2. **draft_chatbot.py**: A simple RAG chatbot that produces the draft answers to be verified.
