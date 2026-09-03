"""Лексический поиск BM25 поверх коллекций Chroma.

Векторный поиск плохо ловит артикулы: запрос «ВА47-63 С16» эмбеддер размажет
по всем автоматическим выключателям. BM25 находит точное вхождение строки,
поэтому в связке эти два метода закрывают слабости друг друга.

Индекс строится в памяти при первом обращении и обновляется, когда меняется
число документов в коллекции (например после загрузки файла пользователем).
"""

from __future__ import annotations

import re
import threading
from dataclasses import dataclass

from rank_bm25 import BM25Okapi

FETCH_BATCH = 5000

_TOKEN_RE = re.compile(r"[a-zA-Zа-яА-ЯёЁ0-9]+")


def tokenize(text: str) -> list[str]:
    """Токены в нижнем регистре; артикулы вида ВА47-63 бьются на части,
    что и нужно — иначе точное совпадение зависело бы от написания дефисов."""
    return _TOKEN_RE.findall(text.lower())


@dataclass
class _Entry:
    doc_id: str
    text: str
    metadata: dict


class _CollectionIndex:
    def __init__(self) -> None:
        self.bm25: BM25Okapi | None = None
        self.entries: list[_Entry] = []
        self.doc_count = -1


_indexes: dict[str, _CollectionIndex] = {}
_lock = threading.Lock()


def _build(collection) -> _CollectionIndex:
    index = _CollectionIndex()
    corpus: list[list[str]] = []
    total = collection.count()

    # пачками: лимит SQLite на число параметров
    for offset in range(0, total, FETCH_BATCH):
        data = collection.get(
            include=["documents", "metadatas"], limit=FETCH_BATCH, offset=offset
        )
        for doc_id, text, meta in zip(data["ids"], data["documents"], data["metadatas"]):
            meta = meta or {}
            searchable = f"{meta.get('doc_title', '')} {meta.get('heading_path', '')} {text}"
            index.entries.append(_Entry(doc_id=doc_id, text=text, metadata=meta))
            corpus.append(tokenize(searchable))

    index.bm25 = BM25Okapi(corpus) if corpus else None
    index.doc_count = total
    return index


def get_index(collection) -> _CollectionIndex:
    """Индекс для коллекции; пересобирается при изменении числа документов."""
    name = collection.name
    with _lock:
        index = _indexes.get(name)
        if index is None or index.doc_count != collection.count():
            index = _build(collection)
            _indexes[name] = index
        return index


def search(collection, query: str, top_k: int) -> list[tuple[str, str, dict, float]]:
    """Возвращает (doc_id, text, metadata, score), лучшие сверху."""
    index = get_index(collection)
    if index.bm25 is None or not index.entries:
        return []

    tokens = tokenize(query)
    if not tokens:
        return []

    scores = index.bm25.get_scores(tokens)
    ranked = sorted(range(len(scores)), key=lambda i: scores[i], reverse=True)[:top_k]
    return [
        (index.entries[i].doc_id, index.entries[i].text, index.entries[i].metadata, float(scores[i]))
        for i in ranked
        if scores[i] > 0
    ]


def invalidate(collection_name: str) -> None:
    with _lock:
        _indexes.pop(collection_name, None)
