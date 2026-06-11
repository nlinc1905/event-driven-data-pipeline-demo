
class DocumentGenerationWorkflow:
    """
    Activity signature for a document generation workflow. 
    The implementation of the activity is defined and runs in workflow-orchestrator.
    """

    @staticmethod
    async def run(workflow_id: str, document: str) -> str:
        return ""


class DocumentProcessingWorkflow:
    """
    Activity signature for a document processing workflow. 
    The implementation of the activity is defined and runs in workflow-orchestrator.
    """

    @staticmethod
    async def run(workflow_id: str, document: str) -> str:
        return ""
