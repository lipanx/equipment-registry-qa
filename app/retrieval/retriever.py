"""Гибридный поиск: векторный + BM25, объединённые через RRF."""

from __future__ import annotations

import re
from dataclasses import dataclass

from app import config
from app.retrieval import bm25_index, parent_store
from app.retrieval.article_match import expand_query
from app.retrieval.vector_store import get_equipment_collection, get_user_collection

CANDIDATES_PER_METHOD = 20
RRF_K = 60
MAX_DOCS_FOR_SECTION_SCAN = 3
MAX_CHUNKS_PER_DOC = 400
SECTION_SCAN_SCORE = 0.02

_PROCEDURAL_QUERY_RE = re.compile(
    r"\b(как\s+(обслуж\w+|провер\w+|эксплуат\w+|монтир\w+|подключ\w+|"
    r"настро\w+|устано\w+)|обслуживани\w+|регламент\w*|порядок\s+\w+|"
    r"периодичн\w+|что\s+делать)\b",
    re.IGNORECASE,
)
_PROCEDURAL_TEXT_RE = re.compile(
    r"(техническо\w+\s+обслуживани\w+|перечень\s+работ|периодичн\w+|"
    r"порядок\s+(технического|проведения|работ)|меры\s+безопасности|"
    r"\d+\s*(мес|месяц\w*|год\w*|лет)\b|осмотр\s+\w+)",
    re.IGNORECASE,
)


@dataclass
class RetrievedChunk:
    text: str           # то, что уйдёт в LLM (родительский блок, если он есть)
    snippet: str        # найденный фрагмент — для показа пользователю
    source_file: str
    source_label: str
    origin: str         # "equipment" | "user"
    score: float        # RRF-score, больше — релевантнее
    vector_distance: float | None = None


def _vector_candidates(collection, query: str, top_k: int) -> list[tuple[str, dict]]:
    if collection.count() == 0:
        return []
    # e5 требует префикса query:
    result = collection.query(
        query_texts=[f"query: {query}"],
        n_results=min(top_k, collection.count()),
        include=["documents", "metadatas", "distances"],
    )
    out = []
    for doc_id, doc, meta, dist in zip(
        result["ids"][0], result["documents"][0], result["metadatas"][0], result["distances"][0]
    ):
        out.append((doc_id, {"text": doc, "meta": meta or {}, "distance": dist}))
    return out


def _bm25_candidates(collection, query: str, top_k: int) -> list[tuple[str, dict]]:
    return [
        (doc_id, {"text": text, "meta": meta, "distance": None})
        for doc_id, text, meta, _score in bm25_index.search(collection, query, top_k)
    ]


def _fuse(ranked_lists: list[list[tuple[str, dict]]]) -> list[tuple[str, dict, float]]:
    """Reciprocal Rank Fusion: документ тем выше, чем лучше его позиции в
    обоих списках. Складываем 1/(k+rank) — так методы объединяются без
    приведения несопоставимых шкал (косинус против BM25-score) к общей."""
    scores: dict[str, float] = {}
    payloads: dict[str, dict] = {}

    for ranked in ranked_lists:
        for rank, (doc_id, payload) in enumerate(ranked, start=1):
            scores[doc_id] = scores.get(doc_id, 0.0) + 1.0 / (RRF_K + rank)
            if doc_id not in payloads:
                payloads[doc_id] = payload
            elif payloads[doc_id].get("distance") is None:
                payloads[doc_id]["distance"] = payload.get("distance")

    fused = [(doc_id, payloads[doc_id], score) for doc_id, score in scores.items()]
    fused.sort(key=lambda x: x[2], reverse=True)
    return fused


def _search_collection(collection, query: str, origin: str) -> list[RetrievedChunk]:
    vector = _vector_candidates(collection, query, CANDIDATES_PER_METHOD)
    lexical = _bm25_candidates(collection, query, CANDIDATES_PER_METHOD)
    if not vector and not lexical:
        return []

    fused = _fuse([vector, lexical])
    parents = parent_store.get_many(
        [p["meta"].get("parent_ref") for _, p, _ in fused if p["meta"].get("parent_ref")]
    )

    chunks: list[RetrievedChunk] = []
    for _doc_id, payload, score in fused:
        meta = payload["meta"]
        snippet = payload["text"]
        chunks.append(
            RetrievedChunk(
                text=parents.get(meta.get("parent_ref", "")) or snippet,
                snippet=snippet,
                source_file=meta.get("source_file", ""),
                source_label=meta.get("source_label", meta.get("source_file", "")),
                origin=origin,
                score=score,
                vector_distance=payload.get("distance"),
            )
        )
    return chunks


def _deduplicate(chunks: list[RetrievedChunk]) -> list[RetrievedChunk]:
    """Соседние фрагменты часто делят один родительский блок — в контексте
    он не нужен дважды."""
    seen: set[str] = set()
    unique: list[RetrievedChunk] = []
    for chunk in chunks:
        key = chunk.text[:300]
        if key in seen:
            continue
        seen.add(key)
        unique.append(chunk)
    return unique


def _boost_procedural(chunks: list[RetrievedChunk], query: str) -> None:
    """Поднимает фрагменты с описанием порядка работ."""
    if not _PROCEDURAL_QUERY_RE.search(query):
        return

    for chunk in chunks:
        matches = len(_PROCEDURAL_TEXT_RE.findall(chunk.text))
        if matches:
            chunk.score *= 1 + min(matches, 5) * 0.15


def _procedural_sections(collection, source_files: list[str], query: str) -> list[RetrievedChunk]:
    """Ищет разделы с порядком работ внутри уже найденных документов."""
    found: list[RetrievedChunk] = []

    for source_file in source_files[:MAX_DOCS_FOR_SECTION_SCAN]:
        data = collection.get(
            where={"source_file": source_file},
            include=["documents", "metadatas"],
            limit=MAX_CHUNKS_PER_DOC,
        )
        best: tuple[int, str, dict] | None = None
        for text, meta in zip(data["documents"], data["metadatas"]):
            matches = len(_PROCEDURAL_TEXT_RE.findall(text))
            if matches and (best is None or matches > best[0]):
                best = (matches, text, meta or {})

        if best is None:
            continue

        matches, text, meta = best
        found.append(
            RetrievedChunk(
                text=parent_store.get(meta.get("parent_ref", "")) or text,
                snippet=text,
                source_file=meta.get("source_file", ""),
                source_label=meta.get("source_label", meta.get("source_file", "")),
                origin="equipment",
                score=SECTION_SCAN_SCORE * min(matches, 6),
            )
        )

    return found


def retrieve(query: str, top_k: int = config.RETRIEVAL_TOP_K) -> list[RetrievedChunk]:
    search_query = expand_query(query)

    equipment = _search_collection(get_equipment_collection(), search_query, "equipment")
    user = _search_collection(get_user_collection(), search_query, "user")

    combined = equipment + user
    _boost_procedural(combined, query)

    if _PROCEDURAL_QUERY_RE.search(query):
        top_sources = list(dict.fromkeys(c.source_file for c in combined if c.source_file))
        combined += _procedural_sections(get_equipment_collection(), top_sources, query)

    combined.sort(key=lambda c: c.score, reverse=True)
    return _deduplicate(combined)[:top_k]
