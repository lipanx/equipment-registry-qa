"""OCR через RapidOCR — лёгкая альтернатива MinerU.

Вместе с кириллической моделью занимает ~25 МБ против ~3 ГБ у MinerU и
работает на onnxruntime, который уже нужен для эмбеддингов. Качество на
сложных таблицах ниже, но паспорта и руководства распознаёт уверенно.

В комплекте RapidOCR идёт только китайско-английская модель распознавания:
без подмены кириллица выходит латиницей («CNCTEMA» вместо «СИСТЕМА»).
Поэтому модель и словарь символов подтягиваются отдельно.
"""

from __future__ import annotations

import threading
from pathlib import Path

REC_MODEL_REPO = "PaddlePaddle/cyrillic_PP-OCRv5_mobile_rec_onnx"
# 200 dpi — компромисс между качеством распознавания и памятью на слабой машине
RENDER_DPI = 200

_lock = threading.Lock()
_engine = None


def _find_key(node, key: str):
    if isinstance(node, dict):
        for name, value in node.items():
            if name == key:
                return value
            found = _find_key(value, key)
            if found is not None:
                return found
    elif isinstance(node, list):
        for value in node:
            found = _find_key(value, key)
            if found is not None:
                return found
    return None


def _prepare_cyrillic_model() -> tuple[str, str]:
    """Возвращает пути к модели распознавания и к словарю символов."""
    import yaml
    from huggingface_hub import snapshot_download

    model_dir = Path(snapshot_download(REC_MODEL_REPO))
    dict_path = model_dir / "cyrillic_dict.txt"

    if not dict_path.exists():
        config = yaml.safe_load((model_dir / "inference.yml").read_text(encoding="utf-8"))
        characters = _find_key(config, "character_dict")
        if not characters:
            raise RuntimeError(f"в {REC_MODEL_REPO} нет словаря символов")
        dict_path.write_text("\n".join(characters), encoding="utf-8")

    return str(model_dir / "inference.onnx"), str(dict_path)


def _get_engine():
    global _engine
    with _lock:
        if _engine is None:
            from rapidocr_onnxruntime import RapidOCR

            rec_model, rec_keys = _prepare_cyrillic_model()
            _engine = RapidOCR(rec_model_path=rec_model, rec_keys_path=rec_keys)
        return _engine


def ocr_pdf(pdf_path: Path, max_pages: int | None = None) -> str:
    """Распознаёт страницы PDF и возвращает текст."""
    import pypdfium2 as pdfium

    engine = _get_engine()
    document = pdfium.PdfDocument(str(pdf_path))
    pages: list[str] = []

    try:
        limit = len(document) if max_pages is None else min(max_pages, len(document))
        for index in range(limit):
            page = document[index]
            try:
                result, _ = engine(page.render(scale=RENDER_DPI / 72).to_pil())
                if result:
                    pages.append(" ".join(line[1] for line in result))
            finally:
                page.close()
    finally:
        document.close()

    return "\n\n".join(pages)
