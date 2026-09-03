"""Точка входа: поднимает сервер в фоне, открывает браузер, живёт в трее."""

from __future__ import annotations

import os
import socket
import sys
import threading
import traceback
import time
import webbrowser

import uvicorn
from PIL import Image, ImageDraw
from pystray import Icon, Menu, MenuItem

from app import config

STARTUP_TIMEOUT = 300

# в сборке без консоли стандартные потоки отсутствуют, а библиотеки
# на них рассчитывают
for _name in ("stdout", "stderr"):
    if getattr(sys, _name, None) is None:
        setattr(sys, _name, open(os.devnull, "w", encoding="utf-8"))


def find_free_port(preferred: int) -> int:
    """Занятый порт — обычная ситуация, поэтому берём следующий свободный."""
    for port in range(preferred, preferred + 20):
        with socket.socket() as probe:
            if probe.connect_ex((config.APP_HOST, port)) != 0:
                return port
    return preferred


def make_icon_image() -> Image.Image:
    img = Image.new("RGB", (64, 64), "#1a1a1a")
    draw = ImageDraw.Draw(img)
    draw.ellipse((12, 12, 52, 52), fill="#4a9eff")
    return img


def wait_until_ready(port: int) -> bool:
    """Первый запуск занимает время: загружается модель и открывается база."""
    deadline = time.monotonic() + STARTUP_TIMEOUT
    while time.monotonic() < deadline:
        with socket.socket() as probe:
            if probe.connect_ex((config.APP_HOST, port)) == 0:
                return True
        time.sleep(0.5)
    return False


def show_error(message: str) -> None:
    try:
        import ctypes

        ctypes.windll.user32.MessageBoxW(0, message, "Инженерный помощник", 0x10)
    except Exception:
        print(message, file=sys.stderr)


def main():
    port = find_free_port(config.APP_PORT)
    url = f"http://{config.APP_HOST}:{port}"

    failure: list[str] = []

    def run_server():
        try:
            # приложение импортируем сами: по строке "app.main:app" uvicorn
            # ищет модуль своим загрузчиком, в собранном exe это не работает.
            # log_config=None — в окне без консоли sys.stdout равен None,
            # а форматтер uvicorn спрашивает у него isatty()
            from app.main import app as application

            uvicorn.run(
                application,
                host=config.APP_HOST,
                port=port,
                log_config=None,
                access_log=False,
            )
        except BaseException:
            failure.append(traceback.format_exc())

    server = threading.Thread(target=run_server, daemon=True)
    server.start()

    if not wait_until_ready(port):
        report = config.WRITABLE_ROOT / "ошибка.txt"
        if failure:
            details = failure[0]
        else:
            # поток ещё работает: показываем, где он застрял, и что нашлось
            # на диске — этого хватает, чтобы отличить долгий старт от сбоя
            details = "\n".join(
                [
                    "Сервер не ответил за %d с." % STARTUP_TIMEOUT,
                    "",
                    "Папка программы: %s" % config.INSTALL_ROOT,
                    "Ресурсы:         %s" % config.BUNDLE_ROOT,
                    "Данные:          %s (есть: %s)" % (config.DATA_DIR, config.DATA_DIR.exists()),
                    "База:            %s (есть: %s)"
                    % (config.CHROMA_DIR, config.CHROMA_DIR.exists()),
                    "Модель:          %s" % config.EMBEDDING_MODEL_DIR,
                    "Ключ:            %s" % ("есть" if config.ROUTERAI_API_KEY else "НЕТ"),
                    "Порт:            %d" % port,
                    "",
                    "Где остановился запуск:",
                    "".join(traceback.format_stack(sys._current_frames().get(server.ident))),
                ]
            )
        try:
            report.parent.mkdir(parents=True, exist_ok=True)
            report.write_text(details, encoding="utf-8")
        except OSError:
            pass
        show_error(f"Не удалось запустить программу.\n\nПодробности: {report}")
        return

    webbrowser.open(url)

    icon = Icon(
        "Инженерный помощник",
        make_icon_image(),
        "Инженерный помощник",
        menu=Menu(
            MenuItem("Открыть", lambda icon, item: webbrowser.open(url), default=True),
            MenuItem("Выход", lambda icon, item: icon.stop()),
        ),
    )
    icon.run()


if __name__ == "__main__":
    main()
