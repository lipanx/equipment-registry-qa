"""Хранение ключа доступа в сборке.

Ключ шифруется, чтобы его нельзя было найти простым просмотром файлов или
поиском строки «sk-» в дистрибутиве. От целенаправленного извлечения это
не защищает: программа расшифровывает ключ на той же машине, где работает,
поэтому ключ для дистрибутива стоит держать отдельным от рабочего и
ограничивать по расходам.

Ключ берётся в таком порядке:
  1. переменная окружения ROUTERAI_API_KEY;
  2. .env рядом с программой;
  3. зашифрованный secret.bin в составе сборки.
"""

from __future__ import annotations

import base64
import hashlib
import os
from pathlib import Path

SECRET_FILE = "secret.bin"
_SALT = b"engineering-assistant-v1"


def _keystream(length: int, seed: bytes) -> bytes:
    out = bytearray()
    counter = 0
    while len(out) < length:
        out += hashlib.sha256(seed + counter.to_bytes(4, "big")).digest()
        counter += 1
    return bytes(out[:length])


def _seed() -> bytes:
    # без привязки к системе: ключ шифруется на машине сборки,
    # а расшифровывается на машине пользователя
    return hashlib.sha256(_SALT).digest()


def encrypt(value: str) -> str:
    data = value.encode("utf-8")
    stream = _keystream(len(data), _seed())
    return base64.b64encode(bytes(a ^ b for a, b in zip(data, stream))).decode("ascii")


def decrypt(payload: str) -> str:
    data = base64.b64decode(payload)
    stream = _keystream(len(data), _seed())
    return bytes(a ^ b for a, b in zip(data, stream)).decode("utf-8")


def load_api_key(bundle_root: Path, env_value: str = "") -> str:
    if env_value:
        return env_value

    secret_path = bundle_root / SECRET_FILE
    if not secret_path.exists():
        return ""

    try:
        return decrypt(secret_path.read_text(encoding="ascii").strip())
    except Exception:
        return ""


def main() -> None:
    """Создаёт secret.bin для сборки: python -m app.secrets_store <ключ>"""
    import sys

    key = sys.argv[1] if len(sys.argv) > 1 else os.getenv("ROUTERAI_API_KEY", "")
    if not key:
        print("Укажите ключ: python -m app.secrets_store sk-...")
        raise SystemExit(1)

    target = Path(__file__).resolve().parent.parent / "build" / SECRET_FILE
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(encrypt(key), encoding="ascii")
    print(f"Ключ записан в {target}")


if __name__ == "__main__":
    main()
