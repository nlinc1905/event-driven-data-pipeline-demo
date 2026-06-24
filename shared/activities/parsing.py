from dataclasses import dataclass

from temporalio import activity


@dataclass
class ParseDocumentRequest:
    document_id: str
    pdf_path: str


@dataclass
class ParseDocumentResponse:
    document_id: str
    markdown: str
    metadata: dict


@activity.defn
async def parse_document(request: ParseDocumentRequest) -> ParseDocumentResponse:
    """
    Activity signature for parsing a document, with the activity name, schema, and serialization definition.
    This is an activity contract that never executes, but is used by the workflow to call the activity by name. 
    The implementation of the activity is defined and runs in parser-service.
    """
    raise NotImplementedError("This is a stub. The real implementation runs in parser-service.")
