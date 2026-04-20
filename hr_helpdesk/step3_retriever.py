# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# Step 3 — Retriever
# Purpose : Connect to pgvector (from Step 2) and retrieve the most
#           relevant policy chunks for a given user question.
# Next    : step4_app.py calls this to build answers in the Streamlit UI.
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
from __future__ import annotations

import logging
import os
from pathlib import Path
from dataclasses import dataclass, field
from typing import Any

from dotenv import load_dotenv
from langchain_core.documents import Document
from langchain_google_genai import GoogleGenerativeAIEmbeddings
from langchain_postgres import PGVector
from sqlalchemy import create_engine

PROJECT_ROOT = Path(__file__).resolve().parents[1]

load_dotenv(PROJECT_ROOT / '.env')

logger = logging.getLogger(__name__)


def _optional_int(name: str) -> int | None:
    value = os.getenv(name)
    return int(value) if value else None


def _is_connection_error(exc: BaseException) -> bool:
    """Detect transient PostgreSQL / SSL connection failures."""
    msg = str(exc).lower()
    return any(marker in msg for marker in (
        "ssl connection has been closed unexpectedly",
        "connection reset",
        "connection refused",
        "server closed the connection unexpectedly",
        "broken pipe",
        "operationalerror",
        "could not connect to server",
        "connection timed out",
        "ssl syscall error",
    ))


@dataclass(slots=True)
class RetrievalConfig:
    connection: str = os.getenv(
        "PGVECTOR_CONNECTION",
        "postgresql+psycopg://postgres:postgres@localhost:5433/akhilaprime_hr",
    )
    collection_name: str = os.getenv("HR_COLLECTION_NAME", "akhilaprime_hr_helpdesk")
    embedding_model: str = os.getenv("EMBEDDING_MODEL", "gemini-embedding-001")
    embedding_dimension: int | None = _optional_int("EMBEDDING_DIMENSION")
    primary_k: int = 6
    primary_fetch_k: int = 24
    mmr_lambda_mult: float = 0.7
    use_threshold_retrieval: bool = True
    score_threshold: float = 0.35
    threshold_k: int = 6
    fallback_k: int = 6
    max_context_docs: int = 6


@dataclass(slots=True)
class RetrievalResult:
    query: str
    normalized_query: str
    inferred_filters: dict[str, Any]
    search_strategy: str
    docs: list[Document] = field(default_factory=list)


def _build_resilient_engine(connection_string: str) -> Any:
    """Create a SQLAlchemy engine with connection pool resilience.

    - pool_pre_ping=True  : Tests connections before handing them out so
                            stale / SSL-dropped connections are discarded
                            automatically instead of raising an error.
    - pool_recycle=300     : Recycle connections every 5 minutes to avoid
                            Neon / cloud PG idle-timeout disconnects.
    - pool_size=2          : Keep a small pool (this is a single-user app).
    - max_overflow=3       : Allow a few extra connections under burst.
    """
    return create_engine(
        connection_string,
        pool_pre_ping=True,
        pool_recycle=300,
        pool_size=2,
        max_overflow=3,
    )


class HRRetrievalPipeline:
    _MAX_RETRIES = 2  # auto-retry once on connection drop

    def __init__(self, config: RetrievalConfig):
        self.config = config
        self.embedding = GoogleGenerativeAIEmbeddings(
            model=config.embedding_model,
            output_dimensionality=config.embedding_dimension,
        )
        self._engine = _build_resilient_engine(config.connection)
        self.vector_store = self._create_vector_store()

    def _create_vector_store(self) -> PGVector:
        """Build (or rebuild) the PGVector store using the resilient engine."""
        return PGVector(
            embeddings=self.embedding,
            connection=self._engine,
            collection_name=self.config.collection_name,
            embedding_length=self.config.embedding_dimension,
            use_jsonb=True,
            create_extension=False,
        )

    def _reconnect(self) -> None:
        """Dispose the old connection pool and rebuild the vector store."""
        logger.warning("Reconnecting to PGVector after connection drop...")
        try:
            self._engine.dispose()
        except Exception:
            pass
        self._engine = _build_resilient_engine(self.config.connection)
        self.vector_store = self._create_vector_store()

    def normalize_query(self, query: str) -> str:
        return " ".join(query.strip().split())

    def retrieve_mmr(self, query: str, metadata_filter: dict[str, Any] | None = None) -> list[Document]:
        retriever = self.vector_store.as_retriever(
            search_type="mmr",
            search_kwargs={
                "k": self.config.primary_k,
                "fetch_k": self.config.primary_fetch_k,
                "lambda_mult": self.config.mmr_lambda_mult,
                "filter": metadata_filter,
            },
        )
        return retriever.invoke(query)

    def retrieve_threshold(self, query: str) -> list[Document]:
        scored_docs = self.vector_store.similarity_search_with_relevance_scores(
            query,
            k=self.config.threshold_k,
        )
        return [doc for doc, score in scored_docs if score >= self.config.score_threshold]

    def retrieve_fallback(self, query: str) -> list[Document]:
        return self.vector_store.similarity_search(query, k=self.config.fallback_k)

    def retrieve(self, query: str) -> RetrievalResult:
        """Retrieve relevant documents with automatic reconnection on SSL/connection drops."""
        last_exc: BaseException | None = None

        for attempt in range(1, self._MAX_RETRIES + 1):
            try:
                return self._retrieve_inner(query)
            except Exception as exc:
                if _is_connection_error(exc) and attempt < self._MAX_RETRIES:
                    logger.warning(
                        "PGVector connection error on attempt %d/%d: %s — reconnecting...",
                        attempt, self._MAX_RETRIES, exc,
                    )
                    last_exc = exc
                    self._reconnect()
                else:
                    raise

        # Should not reach here, but safety fallback
        raise last_exc  # type: ignore[misc]

    def _retrieve_inner(self, query: str) -> RetrievalResult:
        """Core retrieval logic (MMR → threshold → similarity fallback)."""
        normalized_query = self.normalize_query(query)
        docs = self.retrieve_mmr(normalized_query)

        if docs:
            return RetrievalResult(
                query=query,
                normalized_query=normalized_query,
                inferred_filters={},
                search_strategy="mmr",
                docs=docs[: self.config.max_context_docs],
            )

        if self.config.use_threshold_retrieval:
            threshold_docs = self.retrieve_threshold(normalized_query)
            if threshold_docs:
                return RetrievalResult(
                    query=query,
                    normalized_query=normalized_query,
                    inferred_filters={},
                    search_strategy="threshold",
                    docs=threshold_docs[: self.config.max_context_docs],
                )

        fallback_docs = self.retrieve_fallback(normalized_query)
        return RetrievalResult(
            query=query,
            normalized_query=normalized_query,
            inferred_filters={},
            search_strategy="similarity",
            docs=fallback_docs[: self.config.max_context_docs],
        )

    def format_citations(self, docs: list[Document]) -> list[dict[str, str]]:
        citations: list[dict[str, str]] = []
        for doc in docs:
            citations.append(
                {
                    "title": doc.metadata.get("title", "Unknown"),
                    "section_title": doc.metadata.get("section_title", "Unknown"),
                    "source": doc.metadata.get("source", "#"),
                }
            )
        return citations
