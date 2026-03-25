from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends

from supportdoc_rag_chatbot.config import BackendSettings, get_request_settings

from ..schemas import HealthStatusResponse, ReadinessStatusResponse

router = APIRouter(tags=["system"])


@router.get(
    "/healthz",
    response_model=HealthStatusResponse,
    summary="Liveness probe",
)
def get_healthz() -> HealthStatusResponse:
    return HealthStatusResponse(status="ok")


@router.get(
    "/readyz",
    response_model=ReadinessStatusResponse,
    summary="Deterministic readiness probe",
)
def get_readyz(
    settings: Annotated[BackendSettings, Depends(get_request_settings)],
) -> ReadinessStatusResponse:
    return ReadinessStatusResponse(
        status="ready",
        service=settings.app_name,
        environment=settings.environment,
        version=settings.api_version,
    )
