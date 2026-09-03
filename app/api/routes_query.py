import re
from pathlib import Path

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from app import history
from app.generation.router_client import generate_answer
from app.registry.document_registry import find_matching_rows
from app.registry.registry_query import answer_from_registry
from app.retrieval.retriever import retrieve
from app.router import classify, needs_documentation, needs_registry_facts

router = APIRouter()

_REFUSAL_RE = re.compile(
    r"(нет информаци|не найден|не нашл|отсутству|не содержит|не указан|"
    r"не могу|обратит\w+\s+к\s+специалист)",
    re.IGNORECASE,
)


def _relevance_percent(chunk) -> int:
    """Процент уверенности поиска по косинусной дистанции."""
    if chunk.vector_distance is None:
        return 75
    return max(0, min(100, round((1 - chunk.vector_distance / 0.5) * 100)))


LOW_RELEVANCE = 60
THIN_CONTEXT = 2


def _caution(docs: list, facts_text: str, answer: str) -> str | None:
    """Причина перепроверить ответ, если она есть."""
    if facts_text and not docs:
        return None
    if _REFUSAL_RE.search(answer):
        return None

    if not docs:
        return "Ответ дан без опоры на документацию — проверьте сведения сами."

    best = max(d.relevance for d in docs)
    if best < LOW_RELEVANCE:
        return (
            "Подходящих мест в документации не нашлось — ответ может относиться "
            "к другому оборудованию. Сверьтесь с источниками."
        )
    if len(docs) <= THIN_CONTEXT:
        return "Ответ собран по одному-двум фрагментам. Сверьтесь с источниками."
    return None


class ChatRequest(BaseModel):
    question: str


class FoundDoc(BaseModel):
    title: str
    snippet: str
    relevance: int  # 0-100, чтобы человек видел, насколько уверенно нашлось


class ChatResponse(BaseModel):
    answer: str
    sources: list[str]
    registry_rows: list[dict]
    exact_counts: str | None = None
    found_docs: list[FoundDoc] = []
    caution: str | None = None


@router.post("/chat", response_model=ChatResponse)
def chat(req: ChatRequest):
    question = req.question.strip()
    if not question:
        raise HTTPException(400, "Пустой вопрос")

    route = classify(question)

    facts = answer_from_registry(question) if needs_registry_facts(route) else None
    facts_text = facts.as_text() if facts else ""

    chunks = retrieve(question) if needs_documentation(route) or not facts_text else []

    try:
        answer = generate_answer(
            question, chunks, facts_text, history.recent_turns()
        )
    except RuntimeError as exc:
        raise HTTPException(503, str(exc)) from exc

    history.add_turn(question, answer)

    found_docs = [
        FoundDoc(
            title=Path(c.source_label).stem,
            snippet=" ".join(c.snippet.split())[:200],
            relevance=_relevance_percent(c),
        )
        for c in chunks
    ]

    return ChatResponse(
        answer=answer,
        sources=sorted({c.source_label for c in chunks}),
        registry_rows=find_matching_rows(question),
        exact_counts=facts_text or None,
        found_docs=found_docs,
        caution=_caution(found_docs, facts_text, answer),
    )


@router.get("/history")
def get_history(limit: int = 20):
    turns = history.recent_turns(limit=limit)
    return [{"question": t.question, "answer": t.answer} for t in turns]


@router.delete("/history")
def clear_history():
    history.clear()
    return {"status": "cleared"}
