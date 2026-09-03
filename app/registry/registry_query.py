"""Подсчёты и фильтры по Excel-реестру: количество, сроки замены."""

from __future__ import annotations

import datetime as dt
import re
from dataclasses import dataclass, field

from app.registry.document_registry import _load_rows

NAME_KEY = "Наименование и техническая характеристика"
MODEL_KEY = "Тип, марка, модель, модификация, характеристики"
ADDRESS_KEY = "Адрес расположения здания (помещения) НКО"
QTY_KEY = "Количество"
UNIT_KEY = "Ед. изм."
REPLACE_YEAR_KEY = "Нормативный срок замены"

STOP_WORDS = {
    "сколько", "всего", "какие", "какой", "какая", "какое", "есть", "где",
    "они", "она", "оно", "нас", "наш", "нашей", "нашем", "штук", "шт",
    "как", "что", "это", "для", "или", "при", "того", "которые", "который",
    "находится", "находятся", "установлен", "установлены", "установлено",
    "перечисли", "покажи", "список", "выведи", "нужно", "надо", "можно",
    "имеется", "числится", "числятся", "стоит", "стоят", "штуки",
}

COUNT_PATTERNS = re.compile(
    r"\b(скольк\w*|посчита\w+|подсчита\w+|общее\s+количество|суммарн\w+|"
    r"кол-?во|количество)\b",
    re.IGNORECASE,
)
REPLACEMENT_PATTERNS = re.compile(
    r"\b(замен\w+|устарел\w+|просроч\w+|истек\w+|менять|заменить|"
    r"срок\w*\s+служб\w+|ресурс)\b",
    re.IGNORECASE,
)


@dataclass
class RegistryFacts:
    """Посчитанные по реестру факты — подставляются в ответ как достоверные."""

    kind: str  # "count" | "replacement"
    matched_terms: list[str]
    total_positions: int = 0
    total_quantity: float = 0.0
    unit: str = ""
    by_address: dict[str, float] = field(default_factory=dict)
    rows: list[dict] = field(default_factory=list)
    year: int | None = None

    def as_text(self) -> str:
        """Готовая формулировка факта для контекста LLM."""
        if self.kind == "count":
            qty = _fmt_number(self.total_quantity)
            lines = [
                f"Точный подсчёт по реестру для «{' '.join(self.matched_terms)}»: "
                f"{self.total_positions} позиций, суммарно {qty} {self.unit}".strip()
            ]
            if self.by_address:
                lines.append("По адресам:")
                for addr, qty in sorted(self.by_address.items(), key=lambda x: -x[1]):
                    lines.append(f"  - {addr}: {_fmt_number(qty)}")
            return "\n".join(lines)

        lines = [
            f"Точный подсчёт по реестру: {self.total_positions} позиций "
            f"с нормативным сроком замены до {self.year} включительно"
        ]
        for row in self.rows[:20]:
            name = row.get(NAME_KEY, "")
            year = row.get(REPLACE_YEAR_KEY, "")
            addr = row.get(ADDRESS_KEY, "")
            lines.append(f"  - {name} (замена {year}) — {addr}")
        if self.total_positions > 20:
            lines.append(f"  ... и ещё {self.total_positions - 20}")
        return "\n".join(lines)


def _fmt_number(value: float) -> str:
    return str(int(value)) if value == int(value) else f"{value:.1f}"


def _to_float(raw: str) -> float:
    try:
        return float(str(raw).replace(",", ".").strip())
    except (TypeError, ValueError):
        return 0.0


def _to_year(raw: str) -> int | None:
    match = re.search(r"\b(19|20)\d{2}\b", str(raw))
    return int(match.group(0)) if match else None


def significant_words(text: str) -> list[str]:
    words = re.split(r"\W+", text.lower())
    return [w for w in words if len(w) >= 4 and w not in STOP_WORDS]


def _row_matches(row: dict, stems: set[str]) -> bool:
    haystack = f"{row.get(NAME_KEY, '')} {row.get(MODEL_KEY, '')}".lower()
    row_stems = {w[:5] for w in re.split(r"\W+", haystack) if len(w) >= 4}
    return bool(stems & row_stems)


def count_equipment(question: str) -> RegistryFacts | None:
    """Считает позиции и количество по словам из вопроса."""
    words = significant_words(question)
    if not words:
        return None
    stems = {w[:5] for w in words}

    facts = RegistryFacts(kind="count", matched_terms=words)
    units: dict[str, int] = {}

    for row in _load_rows():
        if not _row_matches(row, stems):
            continue
        qty = _to_float(row.get(QTY_KEY, 0))
        facts.total_positions += 1
        facts.total_quantity += qty
        addr = row.get(ADDRESS_KEY, "не указан")
        facts.by_address[addr] = facts.by_address.get(addr, 0) + qty
        unit = row.get(UNIT_KEY, "").strip()
        if unit:
            units[unit] = units.get(unit, 0) + 1
        facts.rows.append(row)

    if facts.total_positions == 0:
        return None
    facts.unit = max(units, key=units.get) if units else ""
    return facts


def find_replacements_due(question: str, year: int | None = None) -> RegistryFacts | None:
    """Позиции, чей нормативный срок замены наступил или уже прошёл."""
    year = year or _to_year(question) or dt.date.today().year

    # убираем слова самой формулировки, оставляем названия оборудования
    words = [
        w for w in significant_words(question)
        if not REPLACEMENT_PATTERNS.fullmatch(w) and not re.fullmatch(r"\d{4}|году?|год", w)
    ]
    facts = RegistryFacts(kind="replacement", matched_terms=words, year=year)
    stems = {w[:5] for w in words} if words else set()

    for row in _load_rows():
        replace_year = _to_year(row.get(REPLACE_YEAR_KEY, ""))
        if replace_year is None or replace_year > year:
            continue
        if stems and not _row_matches(row, stems):
            continue
        facts.total_positions += 1
        facts.rows.append(row)

    facts.rows.sort(key=lambda r: _to_year(r.get(REPLACE_YEAR_KEY, "")) or 9999)
    return facts if facts.total_positions else None


def answer_from_registry(question: str) -> RegistryFacts | None:
    """Главная точка входа: возвращает факты, если вопрос требует подсчёта."""
    if REPLACEMENT_PATTERNS.search(question):
        return find_replacements_due(question)
    if COUNT_PATTERNS.search(question):
        return count_equipment(question)
    return None
