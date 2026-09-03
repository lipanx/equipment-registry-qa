"""Клиент RouterAI (OpenAI-совместимый API)."""

from __future__ import annotations

import time

from openai import OpenAI

from app import config
from app.generation.prompt_templates import SYSTEM_PROMPT, build_user_prompt
from app.history import Turn
from app.retrieval.retriever import RetrievedChunk

TEMPERATURE = 0.1
RETRIES = 3
RETRY_DELAY = 2

_client: OpenAI | None = None


def get_client() -> OpenAI:
    global _client
    if _client is None:
        _client = OpenAI(api_key=config.ROUTERAI_API_KEY, base_url=config.ROUTERAI_BASE_URL)
    return _client


def generate_answer(
    question: str,
    chunks: list[RetrievedChunk],
    registry_facts: str = "",
    history: list[Turn] | None = None,
) -> str:
    if not config.ROUTERAI_API_KEY or not config.ROUTERAI_MODEL:
        missing = "ключ доступа" if not config.ROUTERAI_API_KEY else "модель"
        raise RuntimeError(
            f"Не настроен доступ к сервису ответов: не задана {missing}. "
            "Обратитесь к разработчику."
        )

    messages = [
        {"role": "system", "content": SYSTEM_PROMPT},
        {
            "role": "user",
            "content": build_user_prompt(question, chunks, registry_facts, history),
        },
    ]

    last_error = ""
    for attempt in range(RETRIES):
        try:
            response = get_client().chat.completions.create(
                model=config.ROUTERAI_MODEL,
                temperature=TEMPERATURE,
                messages=messages,
            )
        except Exception as exc:
            last_error = str(exc)
        else:
            # провайдер может вернуть ответ без choices
            if getattr(response, "choices", None):
                return response.choices[0].message.content or ""
            last_error = str(getattr(response, "error", "") or "пустой ответ")

        if attempt < RETRIES - 1:
            time.sleep(RETRY_DELAY * (attempt + 1))

    raise RuntimeError(
        "Сервис ответов недоступен. Проверьте подключение к интернету "
        f"и попробуйте позже. ({last_error[:120]})"
    )
