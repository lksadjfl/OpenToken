# OpenToken UI Architecture

The active MVP UI is served from `static/` by the FastAPI backend.

This directory is retained as a reference area for future frontend work. The current product surface should focus on:

- Account registration and login
- API key creation and revocation
- OpenAI-compatible playground requests
- Usage totals and request logs
- Clear developer-oriented states for errors and empty data

When the project moves to a dedicated Next.js frontend, this reference can be replaced by the new app structure.
