"""Готовит файлы модели для упаковки в дистрибутив.

Модель эмбеддингов по умолчанию скачивается с HuggingFace при первом
обращении. На целевой машине интернета может не быть, поэтому перед сборкой
её кладут рядом с приложением — в build/bundle/model.

Запуск: python build/prepare_bundle.py
"""

from __future__ import annotations

import shutil
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

BUNDLE_DIR = PROJECT_ROOT / "build" / "bundle"
MODEL_DIR = BUNDLE_DIR / "model"

# что реально нужно на целевой машине: квантованная модель и токенизатор.
# Полновесный model.onnx (448 МБ) и model_O4.onnx не берём.
NEEDED_FILES = [
    "onnx/model_qint8_avx512_vnni.onnx",
    "onnx/tokenizer.json",
    "onnx/tokenizer_config.json",
    "onnx/special_tokens_map.json",
    "onnx/config.json",
]


def main() -> None:
    from huggingface_hub import snapshot_download

    from app.retrieval.onnx_embedder import MODEL_REPO

    print(f"Скачиваю {MODEL_REPO}…")
    source = Path(snapshot_download(MODEL_REPO, allow_patterns=["onnx/*", "*.json"]))

    if MODEL_DIR.exists():
        shutil.rmtree(MODEL_DIR)
    (MODEL_DIR / "onnx").mkdir(parents=True)

    total = 0
    for name in NEEDED_FILES:
        src = source / name
        if not src.exists():
            print(f"  ПРОПУЩЕН (нет в репозитории): {name}")
            continue
        dst = MODEL_DIR / name
        shutil.copy(src, dst)
        size = dst.stat().st_size
        total += size
        print(f"  {size / 1024 / 1024:6.1f} МБ  {name}")

    print(f"\nГотово: {total / 1024 / 1024:.0f} МБ в {MODEL_DIR}")

    chroma = PROJECT_ROOT / "data" / "chroma"
    if chroma.exists():
        size = sum(f.stat().st_size for f in chroma.rglob("*") if f.is_file())
        print(f"База ChromaDB: {size / 1024 / 1024:.0f} МБ — попадёт в дистрибутив")
    else:
        print("ВНИМАНИЕ: data/chroma не найдена. Сначала выполните build_index.py")


if __name__ == "__main__":
    main()
