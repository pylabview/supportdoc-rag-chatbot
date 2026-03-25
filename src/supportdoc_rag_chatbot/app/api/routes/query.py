from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends

from supportdoc_rag_chatbot.app.core import QueryOrchestrator, get_request_query_orchestrator
from supportdoc_rag_chatbot.app.schemas import QueryResponse

from ..schemas import QueryRequest

router = APIRouter(tags=["query"])


@router.post(
    "/query",
    response_model=QueryResponse,
    summary="Run backend retrieval, gating, generation, and validation for one question",
)
def post_query(
    payload: QueryRequest,
    orchestrator: Annotated[QueryOrchestrator, Depends(get_request_query_orchestrator)],
) -> QueryResponse:
    return orchestrator.run(payload.question)
