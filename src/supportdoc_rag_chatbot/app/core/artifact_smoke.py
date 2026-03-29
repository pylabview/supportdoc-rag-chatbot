from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from supportdoc_rag_chatbot.ingestion.jsonl import write_jsonl
from supportdoc_rag_chatbot.ingestion.schemas import ChunkRecord
from supportdoc_rag_chatbot.retrieval.embeddings import build_embedding_artifacts
from supportdoc_rag_chatbot.retrieval.embeddings.fixture import (
    DEFAULT_FIXTURE_EMBEDDER_MODEL_NAME,
    create_fixture_embedder,
    write_fixture_embedding_map,
)
from supportdoc_rag_chatbot.retrieval.indexes import build_faiss_index_artifacts

ARTIFACT_SMOKE_SUPPORTED_QUESTION = "What is a Pod?"
ARTIFACT_SMOKE_REFUSAL_QUESTION = "How do I reset my laptop BIOS?"
ARTIFACT_SMOKE_FIXTURE_MODEL_NAME = DEFAULT_FIXTURE_EMBEDDER_MODEL_NAME


@dataclass(slots=True, frozen=True)
class ArtifactApiSmokeFixturePaths:
    root_dir: Path
    chunks_path: Path
    vectors_path: Path
    embedding_metadata_path: Path
    index_path: Path
    index_metadata_path: Path
    row_mapping_path: Path
    embedder_fixture_path: Path
    supported_question: str
    refusal_question: str
    chunk_ids: tuple[str, ...]


def build_artifact_smoke_fixture(root_dir: Path) -> ArtifactApiSmokeFixturePaths:
    resolved_root = root_dir.resolve()
    resolved_root.mkdir(parents=True, exist_ok=True)

    chunks_path = resolved_root / "chunks.jsonl"
    vectors_path = resolved_root / "chunk_embeddings.f32"
    embedding_metadata_path = resolved_root / "chunk_embeddings.metadata.json"
    index_path = resolved_root / "chunk_index.faiss"
    index_metadata_path = resolved_root / "chunk_index.metadata.json"
    row_mapping_path = resolved_root / "chunk_index.row_mapping.json"
    embedder_fixture_path = resolved_root / "query_embedding_fixture.json"

    chunks = _build_artifact_smoke_chunks()
    vectors_by_text = _build_artifact_smoke_vectors(chunks)
    embedder = create_fixture_embedder(
        model_name=ARTIFACT_SMOKE_FIXTURE_MODEL_NAME,
        vectors_by_text=vectors_by_text,
    )

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
    write_fixture_embedding_map(
        embedder_fixture_path,
        model_name=embedder.model_name,
        vectors_by_text=vectors_by_text,
    )

    return ArtifactApiSmokeFixturePaths(
        root_dir=resolved_root,
        chunks_path=chunks_path,
        vectors_path=vectors_path,
        embedding_metadata_path=embedding_metadata_path,
        index_path=index_path,
        index_metadata_path=index_metadata_path,
        row_mapping_path=row_mapping_path,
        embedder_fixture_path=embedder_fixture_path,
        supported_question=ARTIFACT_SMOKE_SUPPORTED_QUESTION,
        refusal_question=ARTIFACT_SMOKE_REFUSAL_QUESTION,
        chunk_ids=tuple(chunk.chunk_id for chunk in chunks),
    )


def render_artifact_smoke_fixture_report(fixture: ArtifactApiSmokeFixturePaths) -> str:
    lines = [
        "Artifact API smoke fixture",
        f"root: {fixture.root_dir}",
        f"chunks: {fixture.chunks_path}",
        f"index: {fixture.index_path}",
        f"index metadata: {fixture.index_metadata_path}",
        f"row mapping: {fixture.row_mapping_path}",
        f"embedder fixture: {fixture.embedder_fixture_path}",
        f"supported question: {fixture.supported_question}",
        f"refusal question: {fixture.refusal_question}",
        f"chunk_ids: {', '.join(fixture.chunk_ids)}",
    ]
    return "\n".join(lines)


def _build_artifact_smoke_chunks() -> tuple[ChunkRecord, ChunkRecord]:
    return (
        ChunkRecord(
            snapshot_id="artifact-smoke-k8s-9e1e32b",
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
            snapshot_id="artifact-smoke-k8s-9e1e32b",
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
    )


def _build_artifact_smoke_vectors(
    chunks: tuple[ChunkRecord, ChunkRecord],
) -> dict[str, list[float]]:
    chunk_one, chunk_two = chunks
    return {
        chunk_one.text: [1.0, 0.0],
        chunk_two.text: [0.8, 0.2],
        ARTIFACT_SMOKE_SUPPORTED_QUESTION: [1.0, 0.0],
        ARTIFACT_SMOKE_REFUSAL_QUESTION: [-1.0, 0.0],
    }


__all__ = [
    "ARTIFACT_SMOKE_FIXTURE_MODEL_NAME",
    "ARTIFACT_SMOKE_REFUSAL_QUESTION",
    "ARTIFACT_SMOKE_SUPPORTED_QUESTION",
    "ArtifactApiSmokeFixturePaths",
    "build_artifact_smoke_fixture",
    "render_artifact_smoke_fixture_report",
]
