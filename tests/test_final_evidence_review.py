from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import Any, Sequence

from fastapi.testclient import TestClient

from supportdoc_rag_chatbot.app.api import create_app
from supportdoc_rag_chatbot.app.client import FixtureGenerationClient
from supportdoc_rag_chatbot.app.core import (
    ArtifactDenseQueryRetriever,
    QueryOrchestrator,
    get_request_query_orchestrator,
)
from supportdoc_rag_chatbot.app.schemas import QueryResponse
from supportdoc_rag_chatbot.config import BackendSettings
from supportdoc_rag_chatbot.ingestion.jsonl import write_jsonl
from supportdoc_rag_chatbot.ingestion.schemas import ChunkRecord
from supportdoc_rag_chatbot.retrieval.embeddings import build_embedding_artifacts
from supportdoc_rag_chatbot.retrieval.indexes import build_faiss_index_artifacts

REVIEW_SET_PATH = Path("data/evaluation/final_evidence_review.k8s-9e1e32b.v1.jsonl")
REVIEW_METADATA_PATH = Path("data/evaluation/final_evidence_review.k8s-9e1e32b.v1.metadata.json")
FIRST_PASS_RAW_PATH = Path("docs/validation/final_evidence_review.first_pass.raw.json")
FINAL_PASS_RAW_PATH = Path("docs/validation/final_evidence_review.final_pass.raw.json")
REVIEW_REPORT_PATH = Path("docs/validation/final_evidence_review.md")
RUBRIC_PATH = Path("docs/validation/final_evidence_review_rubric.md")
RESULTS_TEMPLATE_PATH = Path("docs/validation/final_evidence_review_results.template.md")
README_PATH = Path("README.md")

REVIEW_API_SETTINGS = BackendSettings(
    app_name="SupportDoc Artifact Review API",
    environment="test",
    api_version="9.9.9",
    docs_url="/docs",
    redoc_url="/redoc",
    query_retrieval_mode="artifact",
    query_generation_mode="fixture",
)


@dataclass(slots=True)
class FakeEmbedder:
    vectors_by_text: dict[str, list[float]]
    model_name: str = "fake-embedder"

    def embed_texts(self, texts: Sequence[str]) -> list[list[float]]:
        return [list(self.vectors_by_text[text]) for text in texts]


def _read_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def _read_jsonl(path: Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    with path.open("r", encoding="utf-8") as handle:
        for line in handle:
            payload = line.strip()
            if payload:
                rows.append(json.loads(payload))
    return rows


def _build_review_chunks() -> list[ChunkRecord]:
    return [
        ChunkRecord(
            snapshot_id="k8s-9e1e32b",
            doc_id="content-en-docs-concepts-workloads-pods-pods",
            chunk_id="content-en-docs-concepts-workloads-pods-pods__chunk-0001",
            section_id="content-en-docs-concepts-workloads-pods-pods__section-0001",
            section_index=0,
            chunk_index=0,
            doc_title="Pods",
            section_path=["Concepts", "Workloads", "Pods"],
            source_path="content/en/docs/concepts/workloads/pods/pods.md",
            source_url="https://kubernetes.io/docs/concepts/workloads/pods/",
            license="CC BY 4.0",
            attribution="Kubernetes Documentation © The Kubernetes Authors",
            language="en",
            start_offset=0,
            end_offset=128,
            token_count=20,
            text=(
                "A Pod is the smallest deployable unit in Kubernetes and can run one or more "
                "containers that share network and storage resources."
            ),
        ),
        ChunkRecord(
            snapshot_id="k8s-9e1e32b",
            doc_id="content-en-docs-concepts-workloads-pods-pods",
            chunk_id="content-en-docs-concepts-workloads-pods-pods__chunk-0002",
            section_id="content-en-docs-concepts-workloads-pods-pods__section-0001",
            section_index=0,
            chunk_index=1,
            doc_title="Pods",
            section_path=["Concepts", "Workloads", "Pods"],
            source_path="content/en/docs/concepts/workloads/pods/pods.md",
            source_url="https://kubernetes.io/docs/concepts/workloads/pods/",
            license="CC BY 4.0",
            attribution="Kubernetes Documentation © The Kubernetes Authors",
            language="en",
            start_offset=129,
            end_offset=248,
            token_count=18,
            text=(
                "Pods can also group closely related containers so they share the same network "
                "identity and can coordinate storage resources."
            ),
        ),
    ]


def _build_review_embedder(chunks: Sequence[ChunkRecord]) -> FakeEmbedder:
    chunk_one, chunk_two = chunks
    return FakeEmbedder(
        {
            chunk_one.text: [1.0, 0.0],
            chunk_two.text: [0.7, 0.7],
            "What is a Pod?": [1.0, 0.1],
            "What storage resources do Pods share?": [1.0, -1.0],
            "How do I reset my laptop BIOS?": [-1.0, 0.0],
        }
    )


def _build_expected_review_run(*, run_label: str) -> dict[str, Any]:
    review_rows = _read_jsonl(REVIEW_SET_PATH)
    chunks = _build_review_chunks()
    embedder = _build_review_embedder(chunks)

    with TemporaryDirectory() as tmp_dir:
        tmp_path = Path(tmp_dir)
        chunks_path = tmp_path / "chunks.jsonl"
        embedding_metadata_path = tmp_path / "chunk_embeddings.metadata.json"
        vectors_path = tmp_path / "chunk_embeddings.f32"
        index_path = tmp_path / "chunk_index.faiss"
        index_metadata_path = tmp_path / "chunk_index.metadata.json"
        row_mapping_path = tmp_path / "chunk_index.row_mapping.json"

        write_jsonl(chunks_path, chunks)
        build_embedding_artifacts(
            chunks_path=chunks_path,
            vectors_path=vectors_path,
            metadata_path=embedding_metadata_path,
            embedder=embedder,
            batch_size=2,
        )
        build_faiss_index_artifacts(
            embedding_metadata_path=embedding_metadata_path,
            index_path=index_path,
            metadata_path=index_metadata_path,
            row_mapping_path=row_mapping_path,
        )

        retriever = ArtifactDenseQueryRetriever(
            index_path=index_path,
            metadata_path=index_metadata_path,
            row_mapping_path=row_mapping_path,
            embedder=embedder,
        )
        orchestrator = QueryOrchestrator(
            retriever=retriever,
            generation_client=FixtureGenerationClient(),
        )
        app = create_app(settings=REVIEW_API_SETTINGS)
        app.dependency_overrides[get_request_query_orchestrator] = lambda: orchestrator

        try:
            cases: list[dict[str, Any]] = []
            with TestClient(app) as client:
                for row in review_rows:
                    retrieved = retriever.retrieve(row["question"], top_k=3)
                    response = client.post("/query", json={"question": row["question"]})
                    assert response.status_code == 200
                    payload = QueryResponse.model_validate(response.json()).model_dump(mode="json")
                    cases.append(
                        {
                            "case_id": row["case_id"],
                            "question": row["question"],
                            "expected_outcome": row["expected_outcome"],
                            "expected_reason_code": row["expected_reason_code"],
                            "retrieved": [
                                {
                                    "chunk_id": chunk.chunk_id,
                                    "rank": chunk.rank,
                                    "score": round(chunk.score, 6),
                                }
                                for chunk in retrieved.chunks
                            ],
                            "response": payload,
                        }
                    )
        finally:
            app.dependency_overrides.pop(get_request_query_orchestrator, None)
            orchestrator.close()

    refusal_case_count = sum(1 for row in review_rows if row["expected_outcome"] == "refusal")
    return {
        "review_set_path": str(REVIEW_SET_PATH),
        "run_label": run_label,
        "snapshot_id": "k8s-9e1e32b",
        "backend_path": {
            "api_surface": "FastAPI POST /query",
            "artifact_fixture": "two-chunk Pods excerpt with deterministic fake embedder",
            "generation_mode": "fixture",
            "retrieval_mode": "artifact",
            "retriever_name": "dense-artifact-retriever",
        },
        "cases": cases,
        "summary": {
            "case_count": len(review_rows),
            "refusal_case_count": refusal_case_count,
            "supported_case_count": len(review_rows) - refusal_case_count,
        },
    }


def test_final_evidence_review_package_exists_and_is_linked_from_readme() -> None:
    review_rows = _read_jsonl(REVIEW_SET_PATH)
    metadata = _read_json(REVIEW_METADATA_PATH)
    report = REVIEW_REPORT_PATH.read_text(encoding="utf-8")
    readme = README_PATH.read_text(encoding="utf-8")

    assert len(review_rows) == 3
    assert {row["expected_outcome"] for row in review_rows} == {"supported", "refusal"}
    assert any(row["expected_reason_code"] == "insufficient_evidence" for row in review_rows)
    assert any(row["expected_reason_code"] == "no_relevant_docs" for row in review_rows)

    assert metadata["snapshot_id"] == "k8s-9e1e32b"
    assert metadata["review_report_path"] == str(REVIEW_REPORT_PATH)
    assert metadata["rubric_path"] == str(RUBRIC_PATH)
    assert metadata["results_template_path"] == str(RESULTS_TEMPLATE_PATH)

    assert RUBRIC_PATH.is_file()
    assert RESULTS_TEMPLATE_PATH.is_file()
    assert "## Final pass summary" in report
    assert "## Known limitations" in report
    assert "docs/validation/final_evidence_review.md" in readme
    assert "data/evaluation/final_evidence_review.k8s-9e1e32b.v1.jsonl" in readme


def test_final_evidence_review_raw_artifacts_match_artifact_backed_api_run() -> None:
    assert _read_json(FIRST_PASS_RAW_PATH) == _build_expected_review_run(run_label="first_pass")
    assert _read_json(FINAL_PASS_RAW_PATH) == _build_expected_review_run(run_label="final_pass")
