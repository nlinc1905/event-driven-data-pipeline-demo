from temporalio import activity


@activity.defn
async def parse_document(document: str) -> str:
    """
    Activity signature for parsing a document, with the activity name, schema, and serialization definition.
    This is an activity contract that never executes, but is used by the workflow to call the activity by name. 
    The implementation of the activity is defined and runs in parser-service.
    """
    raise NotImplementedError("This is a stub. The real implementation runs in parser-service.")
