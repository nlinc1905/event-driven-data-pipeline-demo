# Document Generation Service

The generator service ingests documents and runs any processing steps required before saving the data or generating outputs.

## How this Service Runs

When this service runs, it connects to temporal, subscribes to generation-task-queue, and waits for work. When workflows dispatch tasks, it executes document generation activities.
