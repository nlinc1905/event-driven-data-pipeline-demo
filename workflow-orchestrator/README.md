# Workflow Orchestrator

The purpose of this service is to host orchestration workflows and dispatch tasks. It long polls the task queue in Temporal continuously. When it finds a task, it sends it along to the correct worker.

The orchestrator does not know where parser workers live and does not call services directly. Instead, it handles task routing, retries, and persistence.

Think of the orchestrator as a manager who delegates tasks to workers. They manage the queue of tasks.

This service owns:

- workflow definitions
- orchestration logic
- retries
- timeouts
- sequencing of activities

It listens on the workflow-task-queue

Actual work is delegated to:

- parser-service
- generator-service
- other worker services

In production, this separation is extremely valuable because:

- workflows are lightweight/stateful
- activities are compute-heavy
- they scale differently
