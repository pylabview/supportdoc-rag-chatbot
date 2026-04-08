from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING

from supportdoc_rag_chatbot.app.client import GenerationBackendMode
from supportdoc_rag_chatbot.app.core.retrieval import RetrievalBackendMode
from supportdoc_rag_chatbot.app.schemas import (
    DEFAULT_TRUST_ANSWER_FIXTURE_PATH,
    DEFAULT_TRUST_REFUSAL_FIXTURE_PATH,
)
from supportdoc_rag_chatbot.retrieval.embeddings import DEFAULT_CHUNKS_PATH
from supportdoc_rag_chatbot.retrieval.indexes import (
    DEFAULT_FAISS_INDEX_PATH,
    DEFAULT_FAISS_METADATA_PATH,
    DEFAULT_FAISS_ROW_MAPPING_PATH,
)

if TYPE_CHECKING:
    from supportdoc_rag_chatbot.config import BackendSettings


class LocalWorkflowError(RuntimeError):
    """Raised when the local API startup path cannot proceed safely."""


@dataclass(slots=True, frozen=True)
class PreflightCheck:
    name: str
    path: Path
    exists: bool


@dataclass(slots=True, frozen=True)
class LocalApiPreflightReport:
    mode: str
    checks: tuple[PreflightCheck, ...]

    @property
    def is_ready(self) -> bool:
        return all(check.exists for check in self.checks)

    @property
    def missing_paths(self) -> tuple[Path, ...]:
        return tuple(check.path for check in self.checks if not check.exists)


def evaluate_local_api_readiness(settings: BackendSettings) -> LocalApiPreflightReport:
    """Evaluate whether the local API can start in the requested mode."""

    if settings.query_retrieval_mode is RetrievalBackendMode.FIXTURE:
        checks = [
            _check_path("fixture_answer", DEFAULT_TRUST_ANSWER_FIXTURE_PATH),
            _check_path("fixture_refusal", DEFAULT_TRUST_REFUSAL_FIXTURE_PATH),
        ]
    elif settings.query_retrieval_mode is RetrievalBackendMode.ARTIFACT:
        checks = [
            _check_path(
                "chunks", _artifact_path(settings.query_artifact_chunks_path, DEFAULT_CHUNKS_PATH)
            ),
            _check_path(
                "faiss_index",
                _artifact_path(settings.query_artifact_index_path, DEFAULT_FAISS_INDEX_PATH),
            ),
            _check_path(
                "faiss_index_metadata",
                _artifact_path(
                    settings.query_artifact_index_metadata_path,
                    DEFAULT_FAISS_METADATA_PATH,
                ),
            ),
            _check_path(
                "faiss_row_mapping",
                _artifact_path(
                    settings.query_artifact_row_mapping_path,
                    DEFAULT_FAISS_ROW_MAPPING_PATH,
                ),
            ),
        ]
        if settings.query_artifact_embedder_mode == "fixture":
            checks.append(
                _check_path(
                    "artifact_embedder_fixture",
                    _artifact_path(
                        settings.query_artifact_embedder_fixture_path,
                        Path("(unset)"),
                    ),
                )
            )
    else:
        checks = [
            _check_configured("pgvector_dsn", settings.query_pgvector_dsn),
            _check_configured("pgvector_runtime_id", settings.query_pgvector_runtime_id),
        ]
        if settings.query_pgvector_embedder_mode == "fixture":
            checks.append(
                _check_path(
                    "pgvector_embedder_fixture",
                    _artifact_path(
                        settings.query_pgvector_embedder_fixture_path,
                        Path("(unset)"),
                    ),
                )
            )

    if settings.query_generation_mode is GenerationBackendMode.HTTP:
        checks.append(_check_configured("generation_base_url", settings.query_generation_base_url))
    elif settings.query_generation_mode is GenerationBackendMode.OPENAI_COMPATIBLE:
        checks.extend(
            [
                _check_configured("generation_base_url", settings.query_generation_base_url),
                _check_configured("generation_model", settings.query_generation_model),
            ]
        )

    return LocalApiPreflightReport(
        mode=settings.query_retrieval_mode.value,
        checks=tuple(checks),
    )


def ensure_local_api_ready(settings: BackendSettings) -> LocalApiPreflightReport:
    """Raise a clear local-workflow error when the requested mode is not ready."""

    report = evaluate_local_api_readiness(settings)
    if report.is_ready:
        return report

    missing_lines = "\n".join(
        f"- {check.name}: {check.path}" for check in report.checks if not check.exists
    )
    if settings.query_retrieval_mode is RetrievalBackendMode.ARTIFACT:
        raise LocalWorkflowError(
            "Artifact mode requires local retrieval artifacts before the API can start.\n"
            f"Missing inputs:\n{missing_lines}\n"
            "Build local chunk / FAISS artifacts first, or switch to fixture mode with "
            "SUPPORTDOC_QUERY_RETRIEVAL_MODE=fixture for repo-only smoke testing."
        )

    if settings.query_retrieval_mode is RetrievalBackendMode.PGVECTOR:
        raise LocalWorkflowError(
            "pgvector mode requires a reachable PostgreSQL runtime plus the configured query "
            "embedder before the API can start.\n"
            f"Missing inputs:\n{missing_lines}"
        )

    if settings.query_generation_mode is GenerationBackendMode.HTTP:
        raise LocalWorkflowError(
            "HTTP generation mode requires SUPPORTDOC_QUERY_GENERATION_BASE_URL to be set.\n"
            f"Missing inputs:\n{missing_lines}"
        )

    if settings.query_generation_mode is GenerationBackendMode.OPENAI_COMPATIBLE:
        raise LocalWorkflowError(
            "OpenAI-compatible generation mode requires SUPPORTDOC_QUERY_GENERATION_BASE_URL "
            "and SUPPORTDOC_QUERY_GENERATION_MODEL to be set.\n"
            f"Missing inputs:\n{missing_lines}"
        )

    raise LocalWorkflowError(
        "Fixture mode requires the checked-in trust fixtures to exist.\n"
        f"Missing inputs:\n{missing_lines}"
    )


def render_local_api_preflight_report(report: LocalApiPreflightReport) -> str:
    lines = ["Local API preflight", f"mode: {report.mode}"]
    for check in report.checks:
        status = "ok" if check.exists else "missing"
        lines.append(f"- {check.name}: {status} ({check.path})")
    lines.append(f"ready: {'yes' if report.is_ready else 'no'}")
    return "\n".join(lines)


def _check_path(name: str, path: Path | str) -> PreflightCheck:
    resolved = Path(path)
    return PreflightCheck(name=name, path=resolved, exists=resolved.exists())


def _check_configured(name: str, value: str | None) -> PreflightCheck:
    if value is None or not value.strip():
        return PreflightCheck(name=name, path=Path("(unset)"), exists=False)
    return PreflightCheck(name=name, path=Path("(configured)"), exists=True)


def _artifact_path(value: str | None, default: Path) -> Path:
    if value is None:
        return default
    return Path(value)


__all__ = [
    "LocalApiPreflightReport",
    "LocalWorkflowError",
    "PreflightCheck",
    "ensure_local_api_ready",
    "evaluate_local_api_readiness",
    "render_local_api_preflight_report",
]
