# PyInstaller spec для «Инженерного помощника».
#
# Собирать на Windows: PyInstaller не умеет кросс-компиляцию, exe с Linux
# не получить.
#
#   python build\prepare_bundle.py      — положить модель в build\bundle
#   pyinstaller build\app.spec           — собрать
#
# Результат: dist\Инженерный помощник\ — папка с exe, моделью и базой.
# Режим onedir, а не onefile: onefile распаковывает 900 МБ во временную
# папку при каждом запуске, на слабой машине это десятки секунд ожидания.

from pathlib import Path

PROJECT_ROOT = Path(SPECPATH).parent

datas = [
    (str(PROJECT_ROOT / "app" / "static"), "app/static"),
    (str(PROJECT_ROOT / "build" / "bundle" / "model"), "model"),
]

# База и реестр лежат рядом с exe, а не внутри: обновление приложения не
# должно затирать проиндексированные документы пользователя.
binaries = []

hiddenimports = [
    "app.api.routes_query",
    "app.api.routes_documents",
    "app.api.routes_health",
    "app.retrieval.onnx_embedder",
    "uvicorn.logging",
    "uvicorn.loops.auto",
    "uvicorn.protocols.http.auto",
    "uvicorn.protocols.websockets.auto",
    "uvicorn.lifespan.on",
    "pystray._win32",
]

# Тяжёлые пакеты, которые тянутся транзитивно, но не нужны на целевой машине.
excludes = [
    "torch", "torchvision", "torchaudio",
    "transformers", "sentence_transformers",
    "scipy", "sympy", "pandas", "matplotlib",
    "cv2", "PIL.ImageQt",
    "tkinter", "test", "unittest",
    "mineru", "rapidocr_onnxruntime", "paddle",
    "IPython", "jupyter", "notebook",
]

a = Analysis(
    [str(PROJECT_ROOT / "run_app.py")],
    pathex=[str(PROJECT_ROOT)],
    binaries=binaries,
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    runtime_hooks=[],
    excludes=excludes,
    noarchive=False,
)

pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="Инженерный помощник",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    console=False,
    icon=None,
)

coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=False,
    name="Инженерный помощник",
)
