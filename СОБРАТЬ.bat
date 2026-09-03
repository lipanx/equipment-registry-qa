@echo off
chcp 65001 >nul
cd /d "%~dp0"

if not exist .venv (
    echo Создаю окружение...
    py -3.12 -m venv .venv || goto :fail
)

echo Проверяю зависимости...
.venv\Scripts\pip install -q -r build\requirements-build.txt || goto :fail

rem от прошлой сборки остаются старые файлы, чистим
if exist dist rmdir /s /q dist
if exist build\output rmdir /s /q build\output

echo.
echo [1/2] Сборка программы...
.venv\Scripts\pyinstaller --noconfirm build\app.spec || goto :fail

if not exist "dist\EngineerAssistant\EngineerAssistant.exe" (
    echo ОШИБКА: программа не собралась.
    goto :fail
)

echo.
echo [2/2] Сборка установщика...
set ISCC="C:\Program Files (x86)\Inno Setup 6\ISCC.exe"
if not exist %ISCC% (
    echo ОШИБКА: не найден Inno Setup 6.
    echo Скачать: https://jrsoftware.org/isdl.php
    goto :fail
)
%ISCC% build\installer.iss || goto :fail

if not exist "build\output\EngineerAssistant_Setup.exe" (
    echo ОШИБКА: установщик не создался.
    goto :fail
)

copy /y "build\output\EngineerAssistant_Setup.exe" "ГОТОВЫЙ_УСТАНОВЩИК.exe" >nul

echo.
echo ================================================
echo  ГОТОВО
echo.
echo  Готовый установщик лежит в этой папке:
echo      ГОТОВЫЙ_УСТАНОВЩИК.exe
echo.
echo  Это единственный файл, который нужно передать.
echo  Папку dist передавать НЕ нужно, она рабочая.
echo ================================================
pause
exit /b 0

:fail
echo.
echo Сборка прервана. Текст ошибки выше.
pause
exit /b 1
