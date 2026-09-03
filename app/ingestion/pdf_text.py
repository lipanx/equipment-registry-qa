"""Извлечение текста из текстового слоя PDF с коррекцией кодировок.

Если текстового слоя нет, возвращается пустая строка — такой файл идёт
в OCR.
"""

from __future__ import annotations

import logging
import re

from pypdf import PdfReader

logging.getLogger("pypdf").setLevel(logging.ERROR)

_UNI_GLYPH_RE = re.compile(r"/uni([0-9A-Fa-f]{4})")
_LATIN1_RE = re.compile(r"[À-ÿ]")
_CYRILLIC_RE = re.compile(r"[А-яЁё]")
# строка оглавления: текст, точки, номер страницы
_TOC_LINE_RE = re.compile(r"^\s*\S.*?\.{4,}\s*\d+\s*$")

MIN_USEFUL_CHARS = 200


def _decode_uni_glyphs(text: str) -> str:
    return _UNI_GLYPH_RE.sub(lambda m: chr(int(m.group(1), 16)), text)


def _fix_latin1_cyrillic(text: str) -> str:
    return text.encode("latin-1", "ignore").decode("cp1251", "ignore")


def repair_text(text: str) -> str:
    """Чинит два типичных вида искажений кириллицы в текстовом слое PDF."""
    if "/uni" in text:
        text = _decode_uni_glyphs(text)

    latin1 = len(_LATIN1_RE.findall(text))
    if latin1 > 20 and latin1 > len(_CYRILLIC_RE.findall(text)):
        repaired = _fix_latin1_cyrillic(text)
        if len(_CYRILLIC_RE.findall(repaired)) > len(_CYRILLIC_RE.findall(text)):
            text = repaired

    return text


def strip_toc_lines(text: str) -> str:
    """Убирает строки оглавления вида «Название .......... 15»."""
    kept: list[str] = []
    for line in text.split("\n"):
        if _TOC_LINE_RE.match(line):
            continue
        kept.append(line)
    return "\n".join(kept)


def extract_pdf_text(path) -> str:
    """Возвращает текст из текстового слоя PDF; пустая строка если это скан."""
    try:
        reader = PdfReader(str(path))
        raw = "\n\n".join((page.extract_text() or "") for page in reader.pages)
    except Exception:
        return ""

    text = strip_toc_lines(repair_text(raw))
    return text if len(text.strip()) >= MIN_USEFUL_CHARS else ""
