"""Распознавание артикулов в вопросе и приведение к написанию из реестра.

Словарь моделей строится из реестра один раз, LLM не используется.
"""

from __future__ import annotations

import re
import threading
from difflib import SequenceMatcher

from app.registry.document_registry import _load_rows
from app.registry.registry_query import MODEL_KEY, NAME_KEY

# пробел допускается только перед цифрами («ИПР 513-3АМ»)
_CANDIDATE_RE = re.compile(
    r"\b[A-Za-zА-Яа-я]{1,6}[\s\-]?\d{1,4}(?:[\-–.]?[A-Za-zА-Яа-я0-9]{1,6})*"
    r"(?:\s\d{1,4}(?:[\-–.]?[A-Za-zА-Яа-я0-9]{1,6})*)*"
)
SIMILARITY_THRESHOLD = 0.86
MIN_KEY_LENGTH = 4

_lock = threading.Lock()
_catalog: dict[str, str] | None = None


def normalize(text: str) -> str:
    """Ключ для сравнения: только буквы и цифры, латиница похожих букв
    приводится к кириллице («BA47» и «ВА47» — одно и то же)."""
    text = text.lower()
    for latin, cyrillic in (("a", "а"), ("b", "в"), ("c", "с"), ("e", "е"),
                            ("k", "к"), ("m", "м"), ("o", "о"), ("p", "р"),
                            ("t", "т"), ("x", "х"), ("h", "н")):
        text = text.replace(latin, cyrillic)
    return re.sub(r"[^0-9a-zа-я]", "", text)


def _canonical_rank(text: str) -> tuple[int, int]:
    """Чем меньше, тем лучше как каноническое написание."""
    return (text.count(" "), len(text))


def _build_catalog() -> dict[str, str]:
    """{нормализованный ключ: каноническое написание из реестра}."""
    catalog: dict[str, str] = {}
    for row in _load_rows():
        for field in (row.get(MODEL_KEY, ""), row.get(NAME_KEY, "")):
            for raw in _CANDIDATE_RE.findall(field or ""):
                raw = raw.strip()
                key = normalize(raw)
                if len(key) < MIN_KEY_LENGTH or key.isdigit() or key.isalpha():
                    continue
                previous = catalog.get(key)
                if previous is None or _canonical_rank(raw) < _canonical_rank(previous):
                    catalog[key] = raw
    return catalog


def get_catalog() -> dict[str, str]:
    global _catalog
    with _lock:
        if _catalog is None:
            _catalog = _build_catalog()
        return _catalog


def _closest(key: str, catalog: dict[str, str]) -> str | None:
    """Ближайшее написание при опечатке — сравниваем только с ключами
    похожей длины, чтобы не перебирать весь словарь."""
    best_key, best_score = None, SIMILARITY_THRESHOLD
    for candidate in catalog:
        if abs(len(candidate) - len(key)) > 2:
            continue
        score = SequenceMatcher(None, key, candidate).ratio()
        if score > best_score:
            best_key, best_score = candidate, score
    return catalog[best_key] if best_key else None


def find_articles(question: str) -> list[str]:
    """Канонические написания моделей, упомянутых в вопросе."""
    catalog = get_catalog()
    haystack = normalize(question)
    if not haystack:
        return []

    matched: list[str] = []
    for key, canonical in catalog.items():
        if len(key) >= MIN_KEY_LENGTH and key in haystack:
            matched.append(key)

    if not matched:
        return _fuzzy_articles(question, catalog)

    # оставляем только самые полные совпадения
    result: list[str] = []
    for key in sorted(matched, key=len, reverse=True):
        if not any(key in longer for longer in result):
            result.append(key)
    return [catalog[k] for k in result]


def _fuzzy_articles(question: str, catalog: dict[str, str]) -> list[str]:
    """Опечатка: точного вхождения нет, ищем ближайшее написание."""
    found: list[str] = []
    for raw in _CANDIDATE_RE.findall(question):
        key = normalize(raw.strip())
        if len(key) < MIN_KEY_LENGTH or key.isdigit() or key.isalpha():
            continue
        canonical = _closest(key, catalog)
        if canonical and canonical not in found:
            found.append(canonical)
    return found


def expand_query(question: str) -> str:
    """Дополняет вопрос каноническими написаниями найденных моделей.

    Расширенный текст идёт только в поиск; пользователю и LLM показывается
    исходный вопрос.
    """
    articles = find_articles(question)
    if not articles:
        return question

    extra = [a for a in articles if normalize(a) not in normalize(question)]
    return f"{question} {' '.join(extra)}" if extra else question
