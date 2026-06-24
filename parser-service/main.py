import asyncio

from temporalio import activity
from temporalio.worker import Worker

from shared.activities.parsing import parse_document, ParseDocumentRequest, ParseDocumentResponse
from shared.queues import PARSING_TASK_QUEUE
from shared.clients.temporal_client import connect_to_temporal

from pdf_reader import extract_pdf


# =============================================================================
# PARSING ACTIVITY
# =============================================================================

@activity.defn(name=parse_document.__name__)
async def parse_document_implementation(request: ParseDocumentRequest) -> ParseDocumentResponse:
    """
    Implementation of the parse_document activity. This is 
    where the document parsing logic goes. For example, there could be: 
    - OCR
    - parse a PDF
    - extract text
    - chunk content
    - store metadata
    """
    doc_id = request.document_id
    pdf_path = request.pdf_path

    print(f"[Parser] Received PDF file path: {pdf_path}")
    print(f"[Parser] Extracting text from PDF file: {pdf_path}")
    # Docling is CPU bound, so we run it in a separate thread to avoid blocking the event loop
    parsed: dict = await asyncio.to_thread(
        extract_pdf,
        pdf_path,
        None,
    )

    print(f"[Parser] Parsed result: {parsed}")

    return ParseDocumentResponse(
        document_id=doc_id,
        markdown=parsed.get("full_markdown", ""),
        metadata=parsed.get("metadata", {}),
    )


# =============================================================================
# WORKER
# =============================================================================


async def main():

    client = await connect_to_temporal()

    worker = Worker(
        client,
        task_queue=PARSING_TASK_QUEUE,
        activities=[parse_document_implementation],
    )

    print("Parser worker started")
    print(f"Listening on task queue: {PARSING_TASK_QUEUE}")

    await worker.run()


if __name__ == "__main__":
    asyncio.run(main())
