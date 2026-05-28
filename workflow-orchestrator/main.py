import asyncio
from datetime import timedelta

from temporalio.worker import Worker
from temporalio import workflow

from shared.activities.parsing import parse_document
from shared.activities.generation import generate_document
from shared.queues import PARSING_TASK_QUEUE, GENERATION_TASK_QUEUE, WORKFLOW_TASK_QUEUE
from shared.temporal_client import connect_to_temporal


# =============================================================================
# WORKFLOW
# =============================================================================

@workflow.defn
class DocumentProcessingWorkflow:

    @workflow.run
    async def run(self, document: str) -> str:

        workflow.logger.info("Workflow started")

        # ---------------------------------------------------------------------
        # Dispatch parsing activity
        # ---------------------------------------------------------------------

        parsed_result = await workflow.execute_activity(
            parse_document,
            document,
            task_queue=PARSING_TASK_QUEUE,
            start_to_close_timeout=timedelta(seconds=30),
        )

        workflow.logger.info("Parsing completed")

        generation_result = await workflow.execute_activity(
            generate_document,
            parsed_result,
            task_queue=GENERATION_TASK_QUEUE,
            start_to_close_timeout=timedelta(seconds=60),
        )

        workflow.logger.info("Generation completed")
        
        return generation_result


# =============================================================================
# WORKER
# =============================================================================

async def main():

    client = await connect_to_temporal()

    worker = Worker(
        client,
        task_queue=WORKFLOW_TASK_QUEUE,
        workflows=[DocumentProcessingWorkflow],
    )

    print("Workflow orchestrator started")
    print(f"Listening on task queue: {WORKFLOW_TASK_QUEUE}")

    await worker.run()


if __name__ == "__main__":
    asyncio.run(main())
