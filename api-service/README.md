# API Service

The API serves as the entrypoint for back end processes, triggering asynchronous workflows and providing an interface for the application database.

This service owns:

- external API endpoints
- authentication (future)
- request validation
- workflow initiation
- workflow status endpoints (future)

This service SHOULD NOT:

- perform heavy compute
- parse documents
- generate LLM responses
- run long tasks

Instead:

- start Temporal workflows
- return workflow IDs immediately
