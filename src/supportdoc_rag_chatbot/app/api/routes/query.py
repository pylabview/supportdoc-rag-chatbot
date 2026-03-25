from __future__ import annotations

from fastapi import APIRouter

from supportdoc_rag_chatbot.app.schemas import QueryResponse, RefusalReasonCode
from supportdoc_rag_chatbot.app.services import build_refusal_response

from ..schemas import QueryRequest

router = APIRouter(tags=["query"])


@router.post(
    "/query",
    response_model=QueryResponse,
    summary="Validate a query request and return the canonical response envelope",
)
def post_query(payload: QueryRequest) -> QueryResponse:
    del payload
    return build_refusal_response(RefusalReasonCode.NO_RELEVANT_DOCS)
