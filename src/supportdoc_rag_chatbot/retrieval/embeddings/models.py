from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Protocol, Sequence

DEFAULT_LOCAL_EMBEDDING_MODEL = "sentence-transformers/all-MiniLM-L6-v2"
DEFAULT_DEVICE = "cpu"


class DenseEmbedder(Protocol):
    model_name: str

    def embed_texts(self, texts: Sequence[str]) -> list[list[float]]:
        """Return one dense vector per input text in the same row order."""


@dataclass(slots=True)
class SentenceTransformerEmbedder:
    model_name: str = DEFAULT_LOCAL_EMBEDDING_MODEL
    device: str = DEFAULT_DEVICE
    batch_size: int = 32
    normalize_embeddings: bool = True
    show_progress_bar: bool = False
    _model: Any | None = field(default=None, init=False, repr=False)

    def _load_model(self) -> Any:
        if self._model is None:
            try:
                from sentence_transformers import SentenceTransformer
            except ImportError as exc:  # pragma: no cover - depends on optional local extras
                raise RuntimeError(
                    "Local embedding dependencies are not installed. "
                    "Run `uv sync --locked --extra dev-tools --extra embeddings-local`."
                ) from exc

            self._model = SentenceTransformer(self.model_name, device=self.device)
        return self._model

    def embed_texts(self, texts: Sequence[str]) -> list[list[float]]:
        if not texts:
            return []

        model = self._load_model()
        encoded = model.encode(
            list(texts),
            batch_size=self.batch_size,
            show_progress_bar=self.show_progress_bar,
            convert_to_numpy=True,
            normalize_embeddings=self.normalize_embeddings,
        )

        if hasattr(encoded, "tolist"):
            payload = encoded.tolist()
        else:  # pragma: no cover - defensive fallback for alternate backends
            payload = list(encoded)

        return [[float(value) for value in row] for row in payload]


def create_local_embedder(
    *,
    model_name: str = DEFAULT_LOCAL_EMBEDDING_MODEL,
    device: str = DEFAULT_DEVICE,
    batch_size: int = 32,
    normalize_embeddings: bool = True,
) -> DenseEmbedder:
    return SentenceTransformerEmbedder(
        model_name=model_name,
        device=device,
        batch_size=batch_size,
        normalize_embeddings=normalize_embeddings,
    )
