"""Разбиение документа на чанки по схеме parent-child.

Поиск идёт по дочерним фрагментам, в LLM уходит родительский блок.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

# e5-small принимает до 512 токенов
CHILD_CHUNK_CHARS = 700
CHILD_OVERLAP_CHARS = 100
PARENT_MAX_CHARS = 3000
MIN_SECTION_CHARS = 80

HEADING_PATTERN = re.compile(r"^(#{1,6})\s+(.*)$", re.MULTILINE)


@dataclass
class Chunk:
    """Фрагмент для поиска и его окружение для ответа."""

    text: str          # дочерний фрагмент — по нему ищем
    parent_text: str   # родительский блок — его отдаём LLM
    heading_path: str  # «ВА47-60М › Правила монтажа» для контекста при поиске


@dataclass
class _Section:
    heading_path: str
    body: str


def _split_sections(text: str) -> list[_Section]:
    """Режет markdown по заголовкам, запоминая цепочку заголовков."""
    matches = list(HEADING_PATTERN.finditer(text))
    if not matches:
        return [_Section(heading_path="", body=text)]

    sections: list[_Section] = []
    if matches[0].start() > 0:
        head = text[: matches[0].start()]
        if head.strip():
            sections.append(_Section(heading_path="", body=head))

    stack: list[tuple[int, str]] = []
    for i, match in enumerate(matches):
        level = len(match.group(1))
        title = match.group(2).strip()
        while stack and stack[-1][0] >= level:
            stack.pop()
        stack.append((level, title))

        end = matches[i + 1].start() if i + 1 < len(matches) else len(text)
        body = text[match.start():end]
        if body.strip():
            sections.append(
                _Section(heading_path=" › ".join(t for _, t in stack), body=body)
            )

    return _merge_tiny_sections(sections)


def _merge_tiny_sections(sections: list[_Section]) -> list[_Section]:
    """Склеивает заголовки без собственного текста со следующей секцией."""
    merged: list[_Section] = []
    pending: _Section | None = None

    for section in sections:
        if pending is not None:
            section = _Section(
                heading_path=pending.heading_path or section.heading_path,
                body=pending.body + section.body,
            )
            pending = None
        if len(section.body.strip()) < MIN_SECTION_CHARS:
            pending = section
        else:
            merged.append(section)

    if pending is not None:
        if merged:
            merged[-1] = _Section(merged[-1].heading_path, merged[-1].body + pending.body)
        else:
            merged.append(pending)
    return merged


def split_by_size(text: str, chunk_size: int, overlap: int) -> list[str]:
    """Режет текст на части с перекрытием, стараясь резать по границе абзаца."""
    if len(text) <= chunk_size:
        return [text]

    chunks: list[str] = []
    start = 0
    text_len = len(text)
    # границу ищем во второй половине окна, иначе чанк вырождается
    min_boundary_offset = chunk_size // 2

    while start < text_len:
        end = min(start + chunk_size, text_len)
        if end < text_len:
            boundary = text.rfind("\n\n", start + min_boundary_offset, end)
            if boundary != -1:
                end = boundary
        piece = text[start:end].strip()
        if piece:
            chunks.append(piece)
        if end >= text_len:
            break
        start = max(end - overlap, start + min_boundary_offset)

    return chunks


def chunk_rows(text: str) -> list[Chunk]:
    """Для таблиц: строка реестра — неделимый чанк.

    Позицию нельзя резать по размеру: вторая половина остаётся без
    наименования оборудования и в поиске бесполезна.
    """
    return [
        Chunk(text=row.strip(), parent_text=row.strip(), heading_path="")
        for row in text.split("\n\n")
        if row.strip()
    ]


def chunk_document(text: str) -> list[Chunk]:
    """Разбивает документ на дочерние чанки, каждый со своим родителем."""
    result: list[Chunk] = []

    for section in _split_sections(text):
        for parent in split_by_size(section.body, PARENT_MAX_CHARS, 0):
            for child in split_by_size(parent, CHILD_CHUNK_CHARS, CHILD_OVERLAP_CHARS):
                if child.strip():
                    result.append(
                        Chunk(
                            text=child,
                            parent_text=parent,
                            heading_path=section.heading_path,
                        )
                    )

    return result
