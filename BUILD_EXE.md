# Инструкция по созданию .exe файла

## Шаг 1: Установка PyInstaller

Откройте командную строку или PowerShell в папке проекта и выполните:

```bash
pip install -U pyinstaller
```

**Примечание:** Если команда `pyinstaller` не работает после установки, используйте `python -m PyInstaller` вместо `pyinstaller` во всех командах ниже.

## Шаг 2: Создание .exe файла

Выполните одну из следующих команд:

### Вариант 1: Простая команда (рекомендуется)
```bash
python -m PyInstaller --onefile --name="CourseAutomation" --icon=NONE help.py
```

### Вариант 2: С дополнительными опциями (скрытая консоль)
```bash
python -m PyInstaller --onefile --windowed --name="CourseAutomation" help.py
```

### Вариант 3: С включением Excel файлов (рекомендуется)
```bash
python -m PyInstaller --onefile --name="CourseAutomation" --add-data "test.xlsx;." --add-data "test2.xlsx;." help.py
```

## Шаг 3: Найти созданный файл

После выполнения команды, .exe файл будет находиться в папке `dist/CourseAutomation.exe`

## Важные замечания:

1. **ChromeDriver**: 
   - Selenium автоматически скачивает ChromeDriver при первом запуске (начиная с Selenium 4.6+)
   - Если возникают проблемы, убедитесь, что Chrome браузер установлен на системе
   - ChromeDriver будет автоматически скачан в папку пользователя при первом запуске exe

2. **Excel файлы**: 
   - Если используете вариант 3 или build_exe.bat, оба Excel файла (test.xlsx и test2.xlsx) будут включены в exe
   - Файлы будут распакованы во временную папку при запуске exe
   - Убедитесь, что оба файла находятся в папке проекта перед сборкой
   - Программа автоматически использует test.xlsx для модуля 2 (курс 771) и test2.xlsx для следующего курса (курс 772)

3. **Размер файла**: 
   - .exe файл будет довольно большим (50-100 МБ), так как включает Python и все библиотеки
   - Это нормально для Python приложений

4. **Антивирус**: 
   - Некоторые антивирусы могут блокировать .exe файлы, созданные PyInstaller
   - Если это произойдет, добавьте исключение для папки dist/ или для exe файла

## Варианты сборки:

### Вариант 1: Использовать build_exe.bat (рекомендуется для Windows)
Просто запустите `build_exe.bat` двойным кликом - он автоматически установит PyInstaller (если нужно) и создаст exe файл.

### Вариант 2: Использовать .spec файл
```bash
python -m PyInstaller CourseAutomation.spec
```
Этот вариант дает больше контроля над процессом сборки.

### Вариант 3: Ручная команда
```bash
python -m PyInstaller --onefile --name="CourseAutomation" --add-data "test.xlsx;." --add-data "test2.xlsx;." help.py
```

## После создания exe:

1. Найдите файл `dist/CourseAutomation.exe`
2. Скопируйте его в нужную папку
3. Если не использовали --add-data, убедитесь, что файлы `test.xlsx` и `test2.xlsx` находятся в той же папке
4. Запустите exe файл - он должен работать без установленного Python!

