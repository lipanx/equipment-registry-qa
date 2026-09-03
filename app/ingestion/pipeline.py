"""Индексация одного файла в коллекцию ChromaDB: парсинг -> чанкинг -> запись."""

from __future__ import annotations

import hashlib
import logging
import re
from pathlib import Path

from app.ingestion.chunker import chunk_document, chunk_rows
from app.ingestion.loaders import extract_text
from app.retrieval import parent_store
from app.retrieval.vector_store import get_embedding_function

log = logging.getLogger("ingestion")


class DuplicateDocumentError(RuntimeError):
    """Файл с таким содержимым уже есть в коллекции."""


def sha256_of_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def _document_title(path: Path) -> str:
    """Название документа из имени файла без служебного префикса."""
    stem = re.sub(r"^Файл\s*\d+\s*-\s*", "", path.stem)
    return stem.replace("_", " ").strip()


def index_file(collection, path: Path, source_label: str | None = None) -> int:
    """Парсит, чанкует и записывает файл в коллекцию. Возвращает число чанков.

    Если файл (по хэшу содержимого) уже есть в коллекции — пропускается.
    """
    content_hash = sha256_of_file(path)
    existing = collection.get(where={"content_hash": content_hash}, limit=1)
    if existing["ids"]:
        name = (existing["metadatas"][0] or {}).get("source_file", path.name)
        raise DuplicateDocumentError(
            f"Этот документ уже добавлен" + (f" — «{name}»" if name != path.name else "")
        )

    text = extract_text(path)
    if not text.strip():
        raise RuntimeError("пустой текст после парсинга")

    is_table = path.suffix.lower() in {".xlsx", ".csv"}
    chunks = chunk_rows(text) if is_table else chunk_document(text)
    if not chunks:
        log.warning("Не удалось получить чанки: %s", path.name)
        return 0

    title = _document_title(path)
    ids = [f"{content_hash}_{i}" for i in range(len(chunks))]
    parent_refs = parent_store.put_many([c.parent_text for c in chunks])
    metadatas = [
        {
            "source_file": path.name,
            "source_label": source_label or path.name,
            "content_hash": content_hash,
            "chunk_index": i,
            "chunk_count": len(chunks),
            "doc_title": title,
            "heading_path": chunk.heading_path,
            "parent_ref": parent_refs[i],
        }
        for i, chunk in enumerate(chunks)
    ]

    # e5 требует префикса passage:
    documents = [c.text for c in chunks]
    embeddings = get_embedding_function()(
        [
            f"passage: {title}"
            + (f" › {c.heading_path}" if c.heading_path else "")
            + f"\n{c.text}"
            for c in chunks
        ]
    )

    collection.add(ids=ids, documents=documents, metadatas=metadatas, embeddings=embeddings)
    return len(chunks)


def delete_file(collection, content_hash: str) -> None:
    collection.delete(where={"content_hash": content_hash})
