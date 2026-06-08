from temporalio import activity


@activity.defn
async def generate_document(workflow_id: str, document: str) -> str:
    """
    Activity signature for generating a document, with the activity name, schema, and serialization definition.
    This is an activity contract that never executes, but is used by the workflow to call the activity by name. 
    The implementation of the activity is defined and runs in generator-service.
    """
    raise NotImplementedError("This is a stub. The real implementation runs in generator-service.")
