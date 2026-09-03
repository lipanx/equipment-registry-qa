"""Эмбеддинги через ONNX Runtime: квантованная int8-модель e5-small."""

from __future__ import annotations

import threading
from pathlib import Path

import numpy as np
from chromadb.api.types import EmbeddingFunction

MODEL_REPO = "intfloat/multilingual-e5-small"
ONNX_FILE = "onnx/model_qint8_avx512_vnni.onnx"
MAX_LENGTH = 512
BATCH_SIZE = 32


class OnnxEmbedder(EmbeddingFunction):
    """Совместим с chromadb.EmbeddingFunction (embed_query из базового класса)."""

    def __init__(self, model_dir: str | Path | None = None):
        self._model_dir = Path(model_dir) if model_dir else None
        self._lock = threading.Lock()
        self._session = None
        self._tokenizer = None
        self._extra_inputs: set[str] = set()

    @staticmethod
    def name() -> str:
        return "onnx-multilingual-e5-small"

    def _ensure_loaded(self) -> None:
        if self._session is not None:
            return
        with self._lock:
            if self._session is not None:
                return

            import onnxruntime as ort
            from tokenizers import Tokenizer

            model_dir = self._model_dir
            if model_dir is None:
                try:
                    from huggingface_hub import snapshot_download
                except ImportError as exc:
                    raise RuntimeError(
                        "Файлы модели не найдены рядом с приложением. "
                        "Переустановите программу."
                    ) from exc

                model_dir = Path(
                    snapshot_download(MODEL_REPO, allow_patterns=["onnx/*", "*.json"])
                )

            self._tokenizer = Tokenizer.from_file(str(model_dir / "onnx" / "tokenizer.json"))
            self._tokenizer.enable_truncation(max_length=MAX_LENGTH)
            self._tokenizer.enable_padding()
            options = ort.SessionOptions()
            options.graph_optimization_level = ort.GraphOptimizationLevel.ORT_ENABLE_ALL
            self._session = ort.InferenceSession(
                str(model_dir / ONNX_FILE),
                options,
                providers=["CPUExecutionProvider"],
            )
            names = {i.name for i in self._session.get_inputs()}
            self._extra_inputs = names - {"input_ids", "attention_mask"}

    def _encode_batch(self, texts: list[str]) -> np.ndarray:
        encoded = self._tokenizer.encode_batch(texts)
        input_ids = np.array([e.ids for e in encoded], dtype=np.int64)
        attention_mask = np.array([e.attention_mask for e in encoded], dtype=np.int64)

        feed = {"input_ids": input_ids, "attention_mask": attention_mask}
        # граф модели ожидает token_type_ids, XLM-R их не выдаёт
        if "token_type_ids" in self._extra_inputs:
            feed["token_type_ids"] = np.zeros_like(input_ids)

        hidden = self._session.run(None, feed)[0]
        mask = attention_mask[..., None].astype(np.float32)
        pooled = (hidden * mask).sum(axis=1) / np.clip(mask.sum(axis=1), 1e-9, None)
        return pooled / np.clip(np.linalg.norm(pooled, axis=1, keepdims=True), 1e-9, None)

    def __call__(self, input: list[str]) -> list[list[float]]:
        self._ensure_loaded()
        vectors: list[list[float]] = []
        for start in range(0, len(input), BATCH_SIZE):
            batch = self._encode_batch(input[start:start + BATCH_SIZE])
            vectors.extend(batch.astype(np.float32).tolist())
        return vectors
