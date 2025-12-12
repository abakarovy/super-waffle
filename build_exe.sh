#!/bin/bash

echo "========================================"
echo "Создание .exe файла из help.py"
echo "========================================"
echo ""

# Проверяем, установлен ли PyInstaller
if ! python -m pip show pyinstaller &> /dev/null; then
    echo "PyInstaller не установлен. Устанавливаем..."
    python -m pip install pyinstaller
    if [ $? -ne 0 ]; then
        echo "Ошибка при установке PyInstaller!"
        exit 1
    fi
fi

echo ""
echo "Создаем .exe файл..."
echo ""

# Создаем exe файл с включением Excel файла
pyinstaller --onefile \
    --name="CourseAutomation" \
    --add-data "test.xlsx:." \
    --hidden-import=pandas \
    --hidden-import=openpyxl \
    --hidden-import=selenium \
    --collect-all=selenium \
    help.py

if [ $? -ne 0 ]; then
    echo ""
    echo "Ошибка при создании .exe файла!"
    exit 1
fi

echo ""
echo "========================================"
echo "Готово! .exe файл находится в папке dist/"
echo "========================================"
echo ""

