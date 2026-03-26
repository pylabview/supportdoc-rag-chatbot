from __future__ import annotations

from collections.abc import Callable, Iterator

import pytest
from fastapi import FastAPI

from supportdoc_rag_chatbot.app.api import create_app
from supportdoc_rag_chatbot.app.client import GenerationClient
from supportdoc_rag_chatbot.app.core import (
    QueryOrchestrator,
    QueryRetriever,
    get_request_query_orchestrator,
)
from supportdoc_rag_chatbot.config import BackendSettings

API_TEST_SETTINGS = BackendSettings(
    app_name="SupportDoc API Test App",
    environment="test",
    api_version="9.9.9",
    docs_url="/docs",
    redoc_url="/redoc",
    query_retrieval_mode="fixture",
    query_generation_mode="fixture",
)


@pytest.fixture()
def api_test_settings() -> BackendSettings:
    return API_TEST_SETTINGS


@pytest.fixture()
def api_app(api_test_settings: BackendSettings) -> FastAPI:
    return create_app(settings=api_test_settings)


@pytest.fixture()
def override_query_orchestrator(
    api_app: FastAPI,
) -> Iterator[Callable[..., QueryOrchestrator]]:
    created_orchestrators: list[QueryOrchestrator] = []

    def _override(
        *,
        retriever: QueryRetriever,
        generation_client: GenerationClient,
        top_k: int = 3,
        max_generation_attempts: int = 2,
    ) -> QueryOrchestrator:
        orchestrator = QueryOrchestrator(
            retriever=retriever,
            generation_client=generation_client,
            top_k=top_k,
            max_generation_attempts=max_generation_attempts,
        )
        api_app.dependency_overrides[get_request_query_orchestrator] = lambda: orchestrator
        created_orchestrators.append(orchestrator)
        return orchestrator

    try:
        yield _override
    finally:
        api_app.dependency_overrides.pop(get_request_query_orchestrator, None)
        for orchestrator in reversed(created_orchestrators):
            orchestrator.close()
