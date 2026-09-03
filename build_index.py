"""Строит векторную базу ChromaDB из документов реестра инженерного оборудования."""

from __future__ import annotations

import hashlib
import logging
from dataclasses import dataclass
from pathlib import Path

from app import config
from app.ingestion.loaders import SUPPORTED_SUFFIXES
from app.ingestion.pipeline import DuplicateDocumentError, index_file
from app.retrieval.vector_store import get_equipment_collection

logging.basicConfig(level=logging.INFO, format="%(asctime)s | %(levelname)s | %(message)s")
log = logging.getLogger("build_index")



@dataclass
class SourceFile:
    path: Path
    content_hash: str


def sha256_of_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


EXCLUDED_DIR_NAMES = {"chroma", "user_uploads"}


def collect_unique_source_files(data_dir: Path) -> list[SourceFile]:
    """Находит поддерживаемые файлы в data_dir и убирает дубликаты по содержимому.

    Пропускает служебные подпапки (векторная БД, файлы, загруженные через UI) —
    это реестр компании, а не пользовательские загрузки.
    """
    all_files = [
        p for p in data_dir.rglob("*")
        if p.is_file()
        and p.suffix.lower() in SUPPORTED_SUFFIXES
        and not EXCLUDED_DIR_NAMES & set(p.relative_to(data_dir).parts[:-1])
    ]

    by_hash: dict[str, list[Path]] = {}
    for path in all_files:
        by_hash.setdefault(sha256_of_file(path), []).append(path)

    unique: list[SourceFile] = []
    for content_hash, paths in by_hash.items():
        if len(paths) > 1:
            paths.sort(key=lambda p: len(str(p)))
            log.info("Дубликаты (%d шт), оставляю: %s", len(paths), paths[0].name)
            for p in paths[1:]:
                log.info("  пропускаю: %s", p.name)
        unique.append(SourceFile(path=paths[0], content_hash=content_hash))

    log.info("Всего файлов: %d, уникальных: %d", len(all_files), len(unique))
    return unique


def main() -> None:
    collection = get_equipment_collection()

    sources = collect_unique_source_files(config.DATA_DIR)
    # пачками: один get() на десятках тысяч чанков упирается в лимит SQLite
    indexed_hashes: set[str] = set()
    total = collection.count()
    for offset in range(0, total, 5000):
        batch = collection.get(include=["metadatas"], limit=5000, offset=offset)
        indexed_hashes.update(
            m["content_hash"] for m in batch["metadatas"] if m and "content_hash" in m
        )
    to_index = [s for s in sources if s.content_hash not in indexed_hashes]
    log.info("Уже проиндексировано: %d, к индексации: %d", len(sources) - len(to_index), len(to_index))

    total_chunks = 0
    failed: list[str] = []

    for i, source in enumerate(to_index, start=1):
        try:
            chunks = index_file(
                collection, source.path,
                source_label=str(source.path.relative_to(config.DATA_DIR)),
            )
            total_chunks += chunks
            log.info("[%d/%d] %s -> %d чанков", i, len(to_index), source.path.name, chunks)
        except DuplicateDocumentError:
            log.info("[%d/%d] уже в базе: %s", i, len(to_index), source.path.name)
        except Exception:
            log.exception("[%d/%d] Ошибка: %s", i, len(to_index), source.path.name)
            failed.append(source.path.name)

    log.info("Готово. Новых чанков: %d. Коллекция: %s", total_chunks, config.EQUIPMENT_COLLECTION)
    log.info("Всего документов в коллекции: %d", collection.count())
    if failed:
        log.warning("Не удалось обработать %d файлов: %s", len(failed), ", ".join(failed))


if __name__ == "__main__":
    main()
