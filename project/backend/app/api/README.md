## This folder exposes the system through FastAPI.

Routes stay thin. They validate the request, call a service and return the result. No business logic lives here.

### Files included:
1. **`dependencies.py`**: Shared request dependencies such as the current user context.
2. **`routes/`**: The individual API endpoints.
