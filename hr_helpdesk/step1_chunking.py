# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# Step 1 — Chunking
# Purpose : Read markdown HR policy files and split them into sections.
# Next     : step2_indexing.py uses these chunks to create embeddings.
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable


SECTION_PATTERN = re.compile(
    r"(?m)^("
    r"\*\*\d+(?:\.\d+)*\.\s+.*?\*\*"
    r"|\*\*[A-Z][^*]{2,}?:\*\*"
    r"|###\s+\*\*.*?\*\*"
    r")\s*$"
)


@dataclass(slots=True)
class Chunk:
    title: str
    content: str
    chunk_id: int


def clean_heading(raw_heading: str) -> str:
    return raw_heading.replace("###", "").replace("**", "").strip()


def split_markdown_sections(markdown_text: str) -> list[Chunk]:
    parts = SECTION_PATTERN.split(markdown_text)
    chunks: list[Chunk] = []

    for index in range(1, len(parts), 2):
        raw_title = parts[index].strip()
        body = parts[index + 1].strip() if index + 1 < len(parts) else ""
        title = clean_heading(raw_title)
        content = f"{title}\n\n{body}".strip()
        chunks.append(Chunk(title=title, content=content, chunk_id=len(chunks) + 1))

    if chunks:
        return chunks

    fallback = markdown_text.strip()
    return [Chunk(title="Full Document", content=fallback, chunk_id=1)] if fallback else []


def policy_title_from_path(path: Path) -> str:
    return path.stem.replace("_", " ")


def iter_markdown_files(docs_dir: Path) -> Iterable[Path]:
    yield from sorted(docs_dir.glob("*.md"))
