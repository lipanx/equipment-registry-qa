import re
import shutil
import uuid
from pathlib import Path

from fastapi import APIRouter, BackgroundTasks, HTTPException, UploadFile

from app import config
from app.ingestion.loaders import SUPPORTED_SUFFIXES
from app.ingestion.pipeline import DuplicateDocumentError, delete_file, index_file
from app.retrieval import bm25_index
from app.retrieval.vector_store import get_user_collection

router = APIRouter()

MAX_UPLOAD_BYTES = 200 * 1024 * 1024

_uploads: dict[str, dict] = {}


def _process_upload(upload_id: str, path: Path):
    _uploads[upload_id]["status"] = "processing"
    try:
        collection = get_user_collection()
        chunks = index_file(collection, path, source_label=path.name)
        bm25_index.invalidate(collection.name)
        _uploads[upload_id]["status"] = "done"
        _uploads[upload_id]["chunks"] = chunks
    except DuplicateDocumentError as exc:
        # файл принадлежит ранее загруженной копии
        _uploads[upload_id]["status"] = "error"
        _uploads[upload_id]["error"] = str(exc)
    except Exception as exc:
        _uploads[upload_id]["status"] = "error"
        _uploads[upload_id]["error"] = str(exc)
        path.unlink(missing_ok=True)


def _safe_filename(raw: str) -> str:
    """Имя файла без путей: «../../app/main.py» превратится в «main.py».

    Иначе загрузка позволила бы записать файл куда угодно за пределами
    папки загрузок.
    """
    name = Path(raw or "").name
    name = re.sub(r"[^\w\s.()\[\]-]", "_", name, flags=re.UNICODE).strip()
    return name or "upload"


@router.post("/documents")
def upload_document(file: UploadFile, background_tasks: BackgroundTasks):
    filename = _safe_filename(file.filename)
    suffix = Path(filename).suffix.lower()
    if suffix not in SUPPORTED_SUFFIXES:
        raise HTTPException(400, f"Неподдерживаемый формат: {suffix}")

    config.USER_UPLOADS_DIR.mkdir(parents=True, exist_ok=True)
    dest = config.USER_UPLOADS_DIR / filename

    written = 0
    with dest.open("wb") as f:
        while chunk := file.file.read(1024 * 1024):
            written += len(chunk)
            if written > MAX_UPLOAD_BYTES:
                f.close()
                dest.unlink(missing_ok=True)
                raise HTTPException(
                    413, f"Файл больше {MAX_UPLOAD_BYTES // 1024 // 1024} МБ"
                )
            f.write(chunk)

    upload_id = str(uuid.uuid4())
    _uploads[upload_id] = {"status": "queued", "file": filename}
    background_tasks.add_task(_process_upload, upload_id, dest)

    return {"upload_id": upload_id, "status": "queued"}


@router.get("/documents/{upload_id}")
def get_upload_status(upload_id: str):
    if upload_id not in _uploads:
        raise HTTPException(404, "Не найдено")
    return _uploads[upload_id]


@router.get("/documents")
def list_user_documents():
    collection = get_user_collection()
    seen: dict[str, dict] = {}

    # пачками: лимит SQLite на число параметров
    for offset in range(0, collection.count(), 5000):
        batch = collection.get(include=["metadatas"], limit=5000, offset=offset)
        for meta in batch["metadatas"]:
            if not meta:
                continue
            content_hash = meta.get("content_hash")
            if content_hash and content_hash not in seen:
                seen[content_hash] = {
                    "content_hash": content_hash,
                    "source_file": meta.get("source_file", ""),
                    "chunk_count": meta.get("chunk_count", 0),
                }
    return list(seen.values())


@router.delete("/documents/{content_hash}")
def delete_user_document(content_hash: str):
    collection = get_user_collection()

    existing = collection.get(where={"content_hash": content_hash}, limit=1)
    filenames = {m.get("source_file") for m in existing["metadatas"] if m}

    delete_file(collection, content_hash)
    bm25_index.invalidate(collection.name)

    for name in filenames:
        if name:
            (config.USER_UPLOADS_DIR / _safe_filename(name)).unlink(missing_ok=True)

    return {"status": "deleted"}
