"""Классификация вопроса: подсчёт по Excel, поиск по документации или реестру."""

from __future__ import annotations

import re
from enum import Enum

_COUNT_RE = re.compile(
    r"\b(скольк\w*|посчита\w+|подсчита\w+|общее\s+количество|суммарн\w+|кол-?во)\b",
    re.IGNORECASE,
)
_REPLACEMENT_RE = re.compile(
    r"\b(замен\w+|устарел\w+|просроч\w+|истек\w+|менять|заменить|"
    r"срок\w*\s+служб\w+|ресурс\w*)\b",
    re.IGNORECASE,
)
_LOCATION_RE = re.compile(
    r"\b(где\s+(стои\w+|наход\w+|установ\w+|размещ\w+)|в\s+как\w+\s+(помещени\w+|"
    r"здани\w+|корпус\w*)|по\s+как\w+\s+адрес\w*|адрес\w*\s+установк\w+)\b",
    re.IGNORECASE,
)
_DOCS_RE = re.compile(
    r"\b(как\s+(обслуж\w+|подключ\w+|настро\w+|монтир\w+|эксплуат\w+)|"
    r"характеристик\w+|парамет\w+|инструкц\w+|руководств\w+|регламент\w*|"
    r"техническ\w+\s+обслуживани\w+|\bТО\b|схем\w+|номинал\w+)\b",
    re.IGNORECASE,
)


class Route(str, Enum):
    COUNT = "count"              # точный подсчёт по реестру
    REPLACEMENT = "replacement"  # сроки замены по реестру
    LOCATION = "location"        # где установлено — по реестру
    DOCS = "docs"                # регламенты и характеристики — по документации
    GENERAL = "general"          # смешанный вопрос: и реестр, и документация


def classify(question: str) -> Route:
    if _REPLACEMENT_RE.search(question):
        return Route.REPLACEMENT
    if _COUNT_RE.search(question):
        return Route.COUNT
    if _LOCATION_RE.search(question):
        return Route.LOCATION
    if _DOCS_RE.search(question):
        return Route.DOCS
    return Route.GENERAL


def needs_registry_facts(route: Route) -> bool:
    """Нужен ли точный расчёт по Excel вместо ответа модели."""
    return route in (Route.COUNT, Route.REPLACEMENT)


def needs_documentation(route: Route) -> bool:
    """Нужен ли поиск по документации."""
    return route in (Route.DOCS, Route.GENERAL, Route.LOCATION)
