"""Хранилище родительских блоков в SQLite; чанк держит только идентификатор."""

from __future__ import annotations

import hashlib
import sqlite3
import threading
from pathlib import Path

from app import config

_lock = threading.Lock()
_connections: dict[int, sqlite3.Connection] = {}


def _writable_path() -> Path:
    """Блоки загруженных пользователем документов."""
    path = config.WRITABLE_ROOT / "chroma"
    path.mkdir(parents=True, exist_ok=True)
    return path / "parents.db"


def _bundled_path() -> Path:
    """Блоки реестра: поставляются с программой, только читаются."""
    return config.CHROMA_DIR / "parents.db"


def _connect() -> sqlite3.Connection:
    # SQLite не разрешает делить соединение между потоками
    key = threading.get_ident()
    conn = _connections.get(key)
    if conn is None:
        conn = sqlite3.connect(_writable_path(), check_same_thread=False)
        conn.execute(
            "CREATE TABLE IF NOT EXISTS parents (id TEXT PRIMARY KEY, text TEXT NOT NULL)"
        )
        bundled = _bundled_path()
        if bundled.exists() and bundled != _writable_path():
            conn.execute("ATTACH DATABASE ? AS bundled", (str(bundled),))
        _connections[key] = conn
    return conn


def _has_bundled(conn: sqlite3.Connection) -> bool:
    return any(row[1] == "bundled" for row in conn.execute("PRAGMA database_list"))


def parent_id(text: str) -> str:
    return hashlib.sha1(text.encode("utf-8")).hexdigest()[:16]


def put_many(texts: list[str]) -> list[str]:
    """Сохраняет блоки и возвращает их идентификаторы (дубли не пишутся дважды)."""
    ids = [parent_id(t) for t in texts]
    unique: dict[str, str] = dict(zip(ids, texts))
    with _lock:
        conn = _connect()
        conn.executemany(
            "INSERT OR IGNORE INTO parents (id, text) VALUES (?, ?)",
            list(unique.items()),
        )
        conn.commit()
    return ids


def get(parent_ref: str) -> str | None:
    with _lock:
        conn = _connect()
        row = conn.execute("SELECT text FROM parents WHERE id = ?", (parent_ref,)).fetchone()
        if row is None and _has_bundled(conn):
            row = conn.execute(
                "SELECT text FROM bundled.parents WHERE id = ?", (parent_ref,)
            ).fetchone()
    return row[0] if row else None


def get_many(parent_refs: list[str]) -> dict[str, str]:
    if not parent_refs:
        return {}
    result: dict[str, str] = {}
    with _lock:
        conn = _connect()
        tables = ["parents"] + (["bundled.parents"] if _has_bundled(conn) else [])
        # лимит SQLite на число параметров
        for start in range(0, len(parent_refs), 500):
            batch = parent_refs[start:start + 500]
            placeholders = ",".join("?" * len(batch))
            for table in tables:
                rows = conn.execute(
                    f"SELECT id, text FROM {table} WHERE id IN ({placeholders})", batch
                ).fetchall()
                result.update(rows)
    return result
