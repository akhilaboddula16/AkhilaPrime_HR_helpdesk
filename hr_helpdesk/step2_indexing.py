# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# Step 2 — Indexing
# Purpose : Embed the chunks from Step 1 using Gemini and store them
#           in pgvector (PostgreSQL) for fast semantic search.
# Run     : python -m hr_helpdesk.step2_indexing
# Next    : step3_retriever.py pulls these embeddings to answer queries.
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
from __future__ import annotations

import os
import sys
from dataclasses import dataclass
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from dotenv import load_dotenv
from langchain_core.documents import Document
from langchain_google_genai import GoogleGenerativeAIEmbeddings
from langchain_postgres import PGVector
from tqdm import tqdm

from hr_helpdesk.step1_chunking import iter_markdown_files, policy_title_from_path, split_markdown_sections

load_dotenv(PROJECT_ROOT / '.env')


def _optional_int(name: str) -> int | None:
    value = os.getenv(name)
    return int(value) if value else None


@dataclass(slots=True)
class IndexingConfig:
    docs_dir: Path = Path(os.getenv("HR_DOCS_DIR", "docs"))
    connection: str = os.getenv(
        "PGVECTOR_CONNECTION",
        "postgresql+psycopg://postgres:postgres@localhost:5433/akhilaprime_hr",
    )
    collection_name: str = os.getenv("HR_COLLECTION_NAME", "akhilaprime_hr_helpdesk")
    embedding_model: str = os.getenv("EMBEDDING_MODEL", "gemini-embedding-001")
    embedding_dimension: int | None = _optional_int("EMBEDDING_DIMENSION")
    create_extension: bool = os.getenv("PGVECTOR_CREATE_EXTENSION", "true").lower() == "true"
    company: str = "AkhilaPrime Solutions Pvt. Ltd."
    department: str = "HR"


def get_embeddings(config: IndexingConfig) -> GoogleGenerativeAIEmbeddings:
    return GoogleGenerativeAIEmbeddings(
        model=config.embedding_model,
        output_dimensionality=config.embedding_dimension,
    )


def load_policy_documents(config: IndexingConfig) -> list[Document]:
    docs: list[Document] = []

    for path in tqdm(list(iter_markdown_files(config.docs_dir)), desc="Loading policies"):
        markdown_text = path.read_text(encoding="utf-8")
        policy_title = policy_title_from_path(path)

        for chunk in split_markdown_sections(markdown_text):
            docs.append(
                Document(
                    page_content=chunk.content,
                    metadata={
                        "company": config.company,
                        "department": config.department,
                        "title": policy_title,
                        "section_title": chunk.title,
                        "chunk_id": chunk.chunk_id,
                        "source": str(path.as_posix()),
                        "filename": path.name,
                    },
                )
            )

    return docs


def build_vector_store(config: IndexingConfig, reset: bool = True) -> tuple[PGVector, int]:
    embeddings = get_embeddings(config)
    vector_store = PGVector(
        embeddings=embeddings,
        connection=config.connection,
        collection_name=config.collection_name,
        embedding_length=config.embedding_dimension,
        use_jsonb=True,
        create_extension=config.create_extension,
        pre_delete_collection=reset,
    )

    documents = load_policy_documents(config)
    if documents:
        vector_store.add_documents(documents)

    return vector_store, len(documents)


def main() -> None:
    config = IndexingConfig()
    _, count = build_vector_store(config=config, reset=True)
    print(
        f"Indexed {count} chunks from {config.docs_dir} into "
        f"{config.collection_name} on {config.connection}."
    )


if __name__ == "__main__":
    main()
