"""Доступ к коллекциям ChromaDB."""

from __future__ import annotations

import chromadb

from app import config

_readonly_client: chromadb.ClientAPI | None = None
_writable_client: chromadb.ClientAPI | None = None
_embedding_fn = None


def get_client() -> chromadb.ClientAPI:
    """База реестра: поставляется с программой, только читается."""
    global _readonly_client
    if _readonly_client is None:
        config.CHROMA_DIR.mkdir(parents=True, exist_ok=True)
        _readonly_client = chromadb.PersistentClient(path=str(config.CHROMA_DIR))
    return _readonly_client


def get_user_client() -> chromadb.ClientAPI:
    """База пользовательских документов: лежит в профиле, доступна на запись."""
    global _writable_client
    if _writable_client is None:
        path = config.WRITABLE_ROOT / "chroma"
        path.mkdir(parents=True, exist_ok=True)
        _writable_client = chromadb.PersistentClient(path=str(path))
    return _writable_client


def get_embedding_function():
    """ONNX по умолчанию; USE_ONNX_EMBEDDER=0 переключает на torch,
    для этого нужен sentence-transformers (в requirements его нет)."""
    global _embedding_fn
    if _embedding_fn is None:
        if config.USE_ONNX_EMBEDDER:
            from app.retrieval.onnx_embedder import OnnxEmbedder

            _embedding_fn = OnnxEmbedder(config.EMBEDDING_MODEL_DIR)
        else:
            from chromadb.utils.embedding_functions import (
                SentenceTransformerEmbeddingFunction,
            )

            _embedding_fn = SentenceTransformerEmbeddingFunction(
                model_name=config.EMBEDDING_MODEL_NAME
            )
    return _embedding_fn


def get_equipment_collection():
    return get_client().get_or_create_collection(
        name=config.EQUIPMENT_COLLECTION,
        embedding_function=get_embedding_function(),
        metadata={"hnsw:space": "cosine"},
    )


def get_user_collection():
    return get_user_client().get_or_create_collection(
        name=config.USER_COLLECTION,
        embedding_function=get_embedding_function(),
        metadata={"hnsw:space": "cosine"},
    )
