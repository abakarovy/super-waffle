@echo off
echo ========================================
echo Создание .exe файла из help.py
echo ========================================
echo.

REM Проверяем, установлен ли PyInstaller
python -m pip show pyinstaller >nul 2>&1
if errorlevel 1 (
    echo PyInstaller не установлен. Устанавливаем...
    python -m pip install pyinstaller
    if errorlevel 1 (
        echo Ошибка при установке PyInstaller!
        pause
        exit /b 1
    )
)

echo.
echo Создаем .exe файл...
echo.

REM Создаем exe файл с включением Excel файла
pyinstaller --onefile ^
    --name="CourseAutomation" ^
    --add-data "test.xlsx;." ^
    --hidden-import=pandas ^
    --hidden-import=openpyxl ^
    --hidden-import=selenium ^
    --collect-all=selenium ^
    help.py

if errorlevel 1 (
    echo.
    echo Ошибка при создании .exe файла!
    pause
    exit /b 1
)

echo.
echo ========================================
echo Готово! .exe файл находится в папке dist/
echo ========================================
echo.
pause

