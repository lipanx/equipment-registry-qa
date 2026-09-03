"""Настройки приложения, читаются из .env."""

from __future__ import annotations

import os
import sys
from pathlib import Path

from dotenv import load_dotenv

from app.secrets_store import load_api_key

APP_NAME = "Инженерный помощник"
FROZEN = getattr(sys, "frozen", False)

if FROZEN:
    INSTALL_ROOT = Path(sys.executable).parent
    BUNDLE_ROOT = Path(getattr(sys, "_MEIPASS", INSTALL_ROOT))
    # программу могут поставить в Program Files, куда писать нельзя,
    # поэтому изменяемые данные держим в профиле пользователя
    WRITABLE_ROOT = Path(os.getenv("LOCALAPPDATA", Path.home())) / APP_NAME
else:
    INSTALL_ROOT = Path(__file__).resolve().parent.parent
    BUNDLE_ROOT = INSTALL_ROOT
    WRITABLE_ROOT = INSTALL_ROOT / "data"

load_dotenv(INSTALL_ROOT / ".env")

_data_candidates = [BUNDLE_ROOT / "data", INSTALL_ROOT / "_internal" / "data", INSTALL_ROOT / "data"]
DATA_DIR = next((p for p in _data_candidates if p.exists()), INSTALL_ROOT / "data")
CHROMA_DIR = DATA_DIR / "chroma"
REGISTRY_XLSX_PATH = DATA_DIR / "Реестр_оборудования.xlsx"

USER_UPLOADS_DIR = WRITABLE_ROOT / "user_uploads"
HISTORY_PATH = WRITABLE_ROOT / "history.db"

_model_candidates = [
    BUNDLE_ROOT / "model",
    INSTALL_ROOT / "_internal" / "model",
    INSTALL_ROOT / "build" / "bundle" / "model",
]
EMBEDDING_MODEL_DIR = next((p for p in _model_candidates if p.exists()), None)

EQUIPMENT_COLLECTION = "equipment_docs"
USER_COLLECTION = "user_docs"

EMBEDDING_MODEL_NAME = "intfloat/multilingual-e5-small"
USE_ONNX_EMBEDDER = os.getenv("USE_ONNX_EMBEDDER", "1") == "1"

ROUTERAI_API_KEY = (
    load_api_key(BUNDLE_ROOT, os.getenv("ROUTERAI_API_KEY", ""))
    or load_api_key(INSTALL_ROOT / "_internal")
    or load_api_key(INSTALL_ROOT / "build")
)
ROUTERAI_BASE_URL = os.getenv("ROUTERAI_BASE_URL", "https://routerai.ru/api/v1")
ROUTERAI_MODEL = os.getenv("ROUTERAI_MODEL", "mistralai/mistral-small-24b-instruct-2501")

APP_HOST = os.getenv("APP_HOST", "127.0.0.1")
APP_PORT = int(os.getenv("APP_PORT", "8000"))

RETRIEVAL_TOP_K = int(os.getenv("RETRIEVAL_TOP_K", "5"))
