import traceback

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles

from app import config
from app.api import routes_documents, routes_health, routes_query

app = FastAPI(title="Инженерный помощник")


@app.exception_handler(Exception)
async def unhandled_error(request: Request, exc: Exception) -> JSONResponse:
    """Без этого необработанная ошибка уходит страницей HTML, а браузер
    ждёт JSON и показывает невнятное «invalid JSON»."""
    report = config.WRITABLE_ROOT / "ошибка.txt"
    try:
        report.parent.mkdir(parents=True, exist_ok=True)
        report.write_text(traceback.format_exc(), encoding="utf-8")
    except OSError:
        pass
    return JSONResponse(
        status_code=500,
        content={"detail": f"{type(exc).__name__}: {exc}"},
    )

app.include_router(routes_health.router, prefix="/api")
app.include_router(routes_query.router, prefix="/api")
app.include_router(routes_documents.router, prefix="/api")

# путь абсолютный: в собранном приложении рабочая папка не совпадает с кодом
STATIC_DIR = config.BUNDLE_ROOT / "app" / "static"

app.mount("/", StaticFiles(directory=str(STATIC_DIR), html=True), name="static")
