from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field, field_validator


class QueryRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    question: str = Field(description="User question to answer from the local support corpus.")

    @field_validator("question")
    @classmethod
    def _validate_question(cls, value: str) -> str:
        normalized = value.strip()
        if not normalized:
            raise ValueError("question must not be blank")
        return normalized


__all__ = ["QueryRequest"]
