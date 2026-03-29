from __future__ import annotations

import importlib.machinery
import importlib.util
import pickle
import sys
from collections.abc import Callable, Iterator
from pathlib import Path
from types import ModuleType

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


def _numpy():
    import numpy

    return numpy


class _FakeFaissIndexFlatIP:
    def __init__(self, dimension: int) -> None:
        self.d = int(dimension)
        self.ntotal = 0
        self._vectors = _numpy().empty((0, self.d), dtype=_numpy().float32)

    def add(self, vectors) -> None:
        vectors_array = _numpy().asarray(vectors, dtype=_numpy().float32)
        if vectors_array.ndim != 2 or vectors_array.shape[1] != self.d:
            raise ValueError("_FakeFaissIndexFlatIP.add received vectors with the wrong shape")
        self._vectors = _numpy().vstack([self._vectors, vectors_array])
        self.ntotal = int(self._vectors.shape[0])

    def search(self, queries, top_k: int):
        queries_array = _numpy().asarray(queries, dtype=_numpy().float32)
        scores = queries_array @ self._vectors.T
        ranked_indexes = _numpy().argsort(-scores, axis=1, kind="stable")[:, :top_k]
        ranked_scores = _numpy().take_along_axis(scores, ranked_indexes, axis=1)
        return ranked_scores.astype(_numpy().float32), ranked_indexes.astype(_numpy().int64)


def _fake_faiss_module() -> ModuleType:
    def normalize_l2(matrix) -> None:
        array = _numpy().asarray(matrix, dtype=_numpy().float32)
        norms = _numpy().linalg.norm(array, axis=1, keepdims=True)
        norms[norms == 0.0] = 1.0
        array /= norms

    def write_index(index: _FakeFaissIndexFlatIP, path: str) -> None:
        payload = {"d": index.d, "vectors": index._vectors}
        with Path(path).open("wb") as handle:
            pickle.dump(payload, handle)

    def read_index(path: str) -> _FakeFaissIndexFlatIP:
        with Path(path).open("rb") as handle:
            payload = pickle.load(handle)
        index = _FakeFaissIndexFlatIP(payload["d"])
        index.add(payload["vectors"])
        return index

    module = ModuleType("faiss")
    module.__spec__ = importlib.machinery.ModuleSpec(name="faiss", loader=None)
    module.IndexFlatIP = _FakeFaissIndexFlatIP
    module.normalize_L2 = normalize_l2
    module.read_index = read_index
    module.write_index = write_index
    return module


if importlib.util.find_spec("faiss") is None and "faiss" not in sys.modules:
    sys.modules["faiss"] = _fake_faiss_module()


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
