# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# Step 3 — Retriever
# Purpose : Connect to pgvector (from Step 2) and retrieve the most
#           relevant policy chunks for a given user question.
# Next    : step4_app.py calls this to build answers in the Streamlit UI.
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
from __future__ import annotations

import os
from pathlib import Path
from dataclasses import dataclass, field
from typing import Any

from dotenv import load_dotenv
from langchain_core.documents import Document
from langchain_google_genai import GoogleGenerativeAIEmbeddings
from langchain_postgres import PGVector

PROJECT_ROOT = Path(__file__).resolve().parents[1]

load_dotenv(PROJECT_ROOT / '.env')


def _optional_int(name: str) -> int | None:
    value = os.getenv(name)
    return int(value) if value else None


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


class HRRetrievalPipeline:
    def __init__(self, config: RetrievalConfig):
        self.config = config
        self.embedding = GoogleGenerativeAIEmbeddings(
            model=config.embedding_model,
            output_dimensionality=config.embedding_dimension,
        )
        self.vector_store = PGVector(
            embeddings=self.embedding,
            connection=config.connection,
            collection_name=config.collection_name,
            embedding_length=config.embedding_dimension,
            use_jsonb=True,
            create_extension=False,
        )

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
