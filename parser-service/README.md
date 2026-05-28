# Document Parsing Service

The parsing service ingests documents and runs any processing steps required before saving the data or generating outputs.

## How this Service Runs

When this service runs, it connects to temporal, subscribes to parsing-task-queue, and waits for work. When workflows dispatch tasks, it executes document parsing activities.
