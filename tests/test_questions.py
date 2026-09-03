"""Проверка качества ответов на типовых вопросах.

Запуск: .venv/bin/python tests/test_questions.py
Требует поднятого приложения (по умолчанию http://127.0.0.1:8000).

Проверяются не формулировки, а поведение: отказ при отсутствии данных,
точность чисел, отсутствие выдуманных регламентов.
"""

from __future__ import annotations

import os
import re
import sys

import httpx

BASE_URL = os.getenv("APP_URL", "http://127.0.0.1:8000")
TIMEOUT = 120

# Признаки честного отказа
REFUSAL = re.compile(
    r"нет информации|не найден|не нашл|отсутству|не содержит|не указан|"
    r"не могу|обратит\w+ к специалист",
    re.IGNORECASE,
)
# Формулировки, которых в ответе быть не должно — типовые выдумки
HALLUCINATION_MARKERS = re.compile(
    r"смаж|смазк|окислен|протрит|обезжир", re.IGNORECASE
)


class Case:
    def __init__(self, question, must_refuse=False, must_contain=None,
                 must_not_contain=None, needs_exact_counts=False, note=""):
        self.question = question
        self.must_refuse = must_refuse
        self.must_contain = must_contain or []
        self.must_not_contain = must_not_contain or []
        self.needs_exact_counts = needs_exact_counts
        self.note = note


CASES = [
    # --- вопросы вне области ---
    Case("какая завтра погода в Москве", must_refuse=True,
         note="вопрос не про оборудование"),
    Case("напиши письмо начальнику про отпуск", must_refuse=True,
         note="просьба сгенерировать текст"),

    # --- оборудования нет в реестре ---
    Case("расскажи про насос Grundfos CR 15", must_refuse=True,
         note="нет такой позиции — нельзя подменять похожей"),
    Case("характеристики контроллера Siemens S7-1200", must_refuse=True,
         note="нет такой позиции"),

    # --- ложная предпосылка ---
    Case("почему сгорел насос в подвале в марте", must_refuse=True,
         note="события не было — нельзя подтверждать"),

    # --- агрегация: числа только из реестра ---
    Case("сколько всего светильников", needs_exact_counts=True,
         note="считается по Excel, не моделью"),
    Case("сколько у нас автоматических выключателей", needs_exact_counts=True),
    Case("что нужно заменить в 2026 году", needs_exact_counts=True),

    # --- инженерные заключения ---
    Case("можно ли ставить автомат на 40А вместо 16А", must_refuse=True,
         note="решение за инженером, а не за моделью"),
    Case("как обслуживать выключатель ВА47-60М, что делать раз в полгода",
         must_not_contain=["смаж", "окислен"],
         note="регламент только из документации, без выдумок"),

    # --- опечатки и жаргон ---
    Case("характеристики ва4763", note="слитное написание артикула"),
    Case("автомат ВА 47 63", note="артикул через пробелы"),

    # --- нормальные вопросы ---
    Case("какие есть лампы и где они установлены"),
    Case("расскажи про резервный источник питания РИП-12"),
]


def check(client: httpx.Client, case: Case) -> tuple[bool, str]:
    response = client.post("/api/chat", json={"question": case.question})
    if response.status_code != 200:
        return False, f"HTTP {response.status_code}: {response.text[:120]}"

    data = response.json()
    answer = data.get("answer", "")
    problems = []

    if case.must_refuse and not REFUSAL.search(answer):
        problems.append("ожидался отказ, а модель ответила по существу")

    if case.needs_exact_counts and not data.get("exact_counts"):
        problems.append("нет точного подсчёта по реестру")

    for fragment in case.must_contain:
        if fragment.lower() not in answer.lower():
            problems.append(f"нет ожидаемого «{fragment}»")

    for fragment in case.must_not_contain:
        if fragment.lower() in answer.lower():
            problems.append(f"выдумка: «{fragment}»")

    if not case.must_refuse and HALLUCINATION_MARKERS.search(answer):
        problems.append("похоже на типовую выдумку про обслуживание")

    return not problems, "; ".join(problems) or "ok"


def main() -> int:
    failures = 0
    with httpx.Client(base_url=BASE_URL, timeout=TIMEOUT, trust_env=False) as client:
        for i, case in enumerate(CASES, start=1):
            try:
                passed, detail = check(client, case)
            except Exception as exc:
                passed, detail = False, f"исключение: {exc}"

            mark = "OK  " if passed else "FAIL"
            print(f"{mark} {i:2}. {case.question[:52]:54} {detail[:70]}")
            if case.note and not passed:
                print(f"       ожидание: {case.note}")
            failures += not passed

    print(f"\nпройдено {len(CASES) - failures} из {len(CASES)}")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
