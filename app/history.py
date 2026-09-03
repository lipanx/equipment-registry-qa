"""История диалога в SQLite: переживает перезапуск, но не растёт бесконечно."""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from pathlib import Path

from app import config

CONTEXT_TURNS = 3
MAX_STORED_TURNS = 200
MAX_ANSWER_CHARS = 2000


@dataclass
class Turn:
    question: str
    answer: str


def _db_path() -> Path:
    config.HISTORY_PATH.parent.mkdir(parents=True, exist_ok=True)
    return config.HISTORY_PATH


def _connect() -> sqlite3.Connection:
    conn = sqlite3.connect(_db_path())
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS turns (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            question TEXT NOT NULL,
            answer TEXT NOT NULL,
            created_at TEXT NOT NULL DEFAULT (datetime('now'))
        )
        """
    )
    return conn


def add_turn(question: str, answer: str) -> None:
    with _connect() as conn:
        conn.execute(
            "INSERT INTO turns (question, answer) VALUES (?, ?)",
            (question, answer[:MAX_ANSWER_CHARS]),
        )
        conn.execute(
            "DELETE FROM turns WHERE id NOT IN "
            "(SELECT id FROM turns ORDER BY id DESC LIMIT ?)",
            (MAX_STORED_TURNS,),
        )


def recent_turns(limit: int = CONTEXT_TURNS) -> list[Turn]:
    with _connect() as conn:
        rows = conn.execute(
            "SELECT question, answer FROM turns ORDER BY id DESC LIMIT ?", (limit,)
        ).fetchall()
    return [Turn(question=q, answer=a) for q, a in reversed(rows)]


def clear() -> None:
    with _connect() as conn:
        conn.execute("DELETE FROM turns")
