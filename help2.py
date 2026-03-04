import time
import re
from urllib.parse import urlparse, parse_qs, urlencode, urlunparse

import pandas as pd
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC

# Используем уже существующие функции из help.py
from help import (
    setup_driver,
    get_task_form,
    detect_task_type,
    handle_radio_task,
    handle_checkbox_task,
    handle_drag_and_drop_task,
    handle_text_task,
    handle_code_task,
)


def read_answers_excel(excel_path: str = "test2.xlsx") -> pd.DataFrame | None:
    """Читает ответы из Excel (test2.xlsx).
    Ожидаемый формат колонок:
      - 'Вопрос'  – текст вопроса (или его начало)
      - 'Ответ'   – строка с ответом (для radio/checkbox/drag&drop/text)
    Можно добавить дополнительные колонки (например, 'Классворк', 'Страница'),
    скрипт их просто проигнорирует.
    """
    try:
        df = pd.read_excel(excel_path)
        print("=" * 50)
        print(f"Прочитано строк из {excel_path}: {len(df)}")
        print(f"Колонки: {list(df.columns)}")
        print("=" * 50)

        # Ищем колонку вопроса и ответа
        question_col = None
        answer_col = None
        for col in df.columns:
            cl = str(col).lower()
            if "вопрос" in cl or "question" in cl:
                question_col = col
            elif "ответ" in cl or "answer" in cl:
                answer_col = col

        if answer_col is None:
            print("⚠ В Excel (test2.xlsx) не найдена колонка с ответами ('Ответ' / 'Answer').")
            return None

        # Если нет колонки вопроса — тоже работаем, но будем использовать
        # просто порядок строк.
        if question_col is None:
            print("⚠ В Excel не найдена колонка с текстом вопросов ('Вопрос').")
            print("   Будем использовать строки по порядку (первый вопрос → первая строка и т.д.).")

        return df
    except FileNotFoundError:
        print(f"⚠ Файл {excel_path} не найден.")
        return None
    except Exception as e:
        print(f"⚠ Ошибка при чтении Excel {excel_path}: {e}")
        return None


def find_best_answer_row(df: pd.DataFrame, question_text: str) -> int | None:
    """Находит наиболее подходящую строку с ответом по тексту вопроса.
    Используется колонка 'Вопрос' / 'Question'. Если её нет — возвращается
    следующая строка по порядку (не привязываясь к тексту).
    """
    if df is None or len(df) == 0:
        return None

    # Особый случай: формат test2.xlsx
    # Первая колонка называется чем-то вроде "11602" (id урока),
    # а ответы идут строго по порядку — 1-я задача → 1-я строка и т.д.
    # В этом случае просто двигаем курсор по строкам без сопоставления текста.
    numeric_header_cols = [col for col in df.columns if str(col).isdigit()]
    if numeric_header_cols:
        idx = getattr(df, "_cursor_index", 0)
        if idx >= len(df):
            print("  [EXCEL] В test2.xlsx закончились строки с ответами.")
            return None
        df._cursor_index = idx + 1  # type: ignore[attr-defined]
        print(f"  [EXCEL] Используем строку по порядку (test2.xlsx), индекс={idx}")
        return idx

    # Обычный режим: ищем колонку вопроса и сопоставляем по тексту
    question_col = None
    for col in df.columns:
        cl = str(col).lower()
        if "вопрос" in cl or "question" in cl:
            question_col = col
            break

    # Если нет колонки вопроса — используем чисто порядковый индекс
    if question_col is None:
        # Храним текущий индекс в атрибуте DataFrame, чтобы двигаться по строкам
        idx = getattr(df, "_cursor_index", 0)
        if idx >= len(df):
            print("⚠ В Excel закончились строки с ответами.")
            return None
        df._cursor_index = idx + 1  # type: ignore[attr-defined]
        return idx

    import difflib

    q_norm = " ".join(str(question_text).lower().split())
    best_idx = None
    best_score = 0.0

    for i, val in enumerate(df[question_col].astype(str).tolist()):
        v_norm = " ".join(val.lower().split())
        if not v_norm:
            continue
        score = difflib.SequenceMatcher(None, q_norm, v_norm).ratio()
        if score > best_score:
            best_score = score
            best_idx = i

    print(f"  [EXCEL] Лучшее совпадение вопроса: индекс={best_idx}, score={best_score:.2%}")

    # Для test2.xlsx вопросы могут отличаться по формулировке,
    # поэтому снижаем порог до 20% и, если всё равно мало,
    # возвращаем лучший индекс, но с варнингом.
    if best_idx is not None and best_score >= 0.2:
        return best_idx

    if best_idx is not None:
        print("  [EXCEL] ⚠ Низкое совпадение, но всё равно используем лучшую строку.")
        return best_idx

    print("  [EXCEL] Не найдено строки в Excel (df пустой или нет подходящих значений).")
    return None


def get_current_question_text(driver) -> str:
    """Возвращает текст текущего вопроса на странице classworks."""
    try:
        # Основной блок вопроса внутри classwork страницы
        # Обычно текст внутри #taskContentInTaskView
        try:
            content = driver.find_element(By.CSS_SELECTOR, "#taskContentInTaskView")
            text = content.text.strip()
            if text:
                return text
        except Exception:
            pass

        # Фоллбек — берём текст внутри самого form / task блока
        try:
            form = driver.find_element(By.ID, "taskForm")
            text = form.text.strip()
            return text
        except Exception:
            pass
    except Exception as e:
        print(f"  ⚠ Не удалось извлечь текст вопроса: {e}")

    return ""


def process_single_classwork_task(driver, df: pd.DataFrame) -> bool:
    """Обрабатывает один task на странице /classworks/.../tasks/...."""
    current_url = driver.current_url
    print("\n" + "=" * 50)
    print(f"Обрабатываем classwork задачу: {current_url}")
    print("=" * 50)

    # Текст вопроса
    question_text = get_current_question_text(driver)
    print(f"  Текст вопроса (первые 200 символов): '{question_text[:200]}...'")

    # Ищем ответ в Excel
    row_idx = find_best_answer_row(df, question_text)
    if row_idx is None:
        print("  ⚠ Не удалось найти соответствующую строку в Excel.")
        return False

    # Находим колонку ответа
    answer_col = None
    for col in df.columns:
        cl = str(col).lower()
        if "ответ" in cl or "answer" in cl:
            answer_col = col
            break

    if answer_col is None:
        print("  ⚠ В Excel нет колонки с ответами.")
        return False

    answer_text = str(df.iloc[row_idx][answer_col]).strip()
    print(f"  Ответ из Excel для этой задачи: '{answer_text[:200]}...'")

    # Определяем тип задачи и применяем ответ
    task_form = get_task_form(driver)
    if not task_form:
        print("  ⚠ Не удалось найти форму задачи (taskForm).")
        return False

    print("  Определяем тип задачи...")
    task_type = detect_task_type(driver)
    print(f"  Тип задачи: {task_type.upper() if isinstance(task_type, str) else task_type}")

    success = False

    if task_type == "radio":
        success = handle_radio_task(driver, answer_text)
    elif task_type == "checkbox":
        # Checkbox: ожидаем либо строку с разделителем ';', либо переносами строк
        parts = [p.strip() for p in re.split(r"[;\n]+", answer_text) if p.strip()]
        success = handle_checkbox_task(driver, parts)
    elif task_type == "drag_and_drop":
        from help import parse_drag_and_drop_answer  # type: ignore

        mappings = parse_drag_and_drop_answer(answer_text)
        if mappings:
            success = handle_drag_and_drop_task(driver, mappings)
        else:
            print("  ⚠ Не удалось распарсить drag and drop ответ из Excel.")
            success = False
    elif task_type == "text":
        success = handle_text_task(driver, answer_text)
    elif task_type == "code":
        success = handle_code_task(driver, answer_text)
    else:
        print(f"  ⚠ Неизвестный тип задачи: {task_type}")
        success = False

    # Отправляем форму, если всё прошло успешно
    if success:
        print("  ✓ Задача обработана, отправляем форму...")
        try:
            # Кнопка "Ответить" в classworks
            submit_button = driver.find_element(
                By.CSS_SELECTOR,
                "button[type='submit'].fox-Button, button.actions_button__3GaLH",
            )
            driver.execute_script(
                "arguments[0].scrollIntoView({block: 'center'});", submit_button
            )
            time.sleep(0.3)
            submit_button.click()
            time.sleep(2)
            print("  ✓ Форма отправлена (classwork).")
            return True
        except Exception as e:
            print(f"  ⚠ Не удалось отправить форму classwork: {e}")
            return False

    print("  ⚠ Не удалось обработать задачу.")
    return False


def goto_tasks_from_lesson(driver, lesson_url: str) -> str | None:
    """Открывает страницу урока /courses/.../lessons/... и кликает
    по плитке 'Перейти к заданиям'. Возвращает URL classwork страницы."""
    print("\n" + "=" * 50)
    print(f"Открываем урок: {lesson_url}")
    print("=" * 50)
    driver.get(lesson_url)
    time.sleep(2)

    wait = WebDriverWait(driver, 10)

    # Ищем плитку 'Перейти к заданиям'
    try:
        task_card = wait.until(
            EC.element_to_be_clickable(
                (
                    By.XPATH,
                    "//div[contains(@class, 'plate-annex__TailSection') or contains(@class, 'plate-annex__TailSection-kXvpSN')]"
                    "[.//div[contains(text(), 'Перейти к') and contains(text(), 'заданиям')]]",
                )
            )
        )
        print("✓ Найдена плитка 'Перейти к заданиям', кликаем...")
        driver.execute_script("arguments[0].scrollIntoView({block: 'center'});", task_card)
        time.sleep(0.5)
        try:
            task_card.click()
        except Exception:
            driver.execute_script("arguments[0].click();", task_card)
        time.sleep(3)
    except Exception as e:
        print(f"⚠ Не удалось найти плитку 'Перейти к заданиям': {e}")
        return None

    current_url = driver.current_url
    print(f"✓ Перешли на страницу classworks: {current_url}")
    if "/classworks/" in current_url:
        return current_url
    return None


def iterate_classwork_pages(driver, df: pd.DataFrame, max_tasks: int = 3):
    """Проходит по задачам classwork, инкрементируя ID задачи в URL.
    Пример: /classworks/1792/tasks/1191263 → 1191264 → 1191265"""
    from urllib.parse import urlparse, urlunparse

    # Берем текущий URL и вытаскиваем из него ID задачи после /tasks/
    current_url = driver.current_url
    parsed = urlparse(current_url)
    path = parsed.path  # /classworks/1792/tasks/1191263

    m = re.search(r"(\/classworks\/\d+\/tasks\/)(\d+)", path)
    if not m:
        print(f"⚠ Не удалось распарсить ID задачи из URL: {current_url}")
        return

    base_prefix = m.group(1)  # "/classworks/1792/tasks/"
    start_id = int(m.group(2))  # 1191263

    for i in range(max_tasks):
        task_id = start_id + i
        new_path = f"{base_prefix}{task_id}"
        # Оставляем исходный query (page=1 и т.п. как есть)
        new_url = urlunparse(parsed._replace(path=new_path))

        print("\n" + "=" * 50)
        print(f"Переходим на задачу ID={task_id}: {new_url}")
        print("=" * 50)
        driver.get(new_url)
        time.sleep(2)

        # Проверяем, действительно ли есть задача (form id="taskForm")
        try:
            WebDriverWait(driver, 5).until(
                EC.presence_of_element_located((By.ID, "taskForm"))
            )
        except Exception:
            print("⚠ На этой задаче нет формы (taskForm). Пропускаем.")
            continue

        process_single_classwork_task(driver, df)


def main():
    print("=" * 60)
    print("Автоматизация classworks (новый формат заданий)")
    print("=" * 60)
    print("\nЭтот скрипт:")
    print("- открывает урок /courses/.../lessons/...")
    print("- кликает 'Перейти к заданиям'")
    print("- проходит по страницам /classworks/.../tasks?...")
    print("- ищет текст вопроса в test2.xlsx и подставляет ответ\n")

    # Читаем Excel
    df = read_answers_excel("test2.xlsx")
    if df is None:
        return

    driver = setup_driver()
    if not driver:
        print("⚠ Не удалось создать драйвер браузера.")
        return

    # Сразу открываем главную страницу kb.cifrium.ru
    try:
        driver.get("https://kb.cifrium.ru/")
        print("✓ Открыта главная страница kb.cifrium.ru")
    except Exception as e:
        print(f"⚠ Не удалось открыть kb.cifrium.ru: {e}")

    # Пользователь сам должен быть залогинен в браузере
    input("\nВойдите в аккаунт на kb.cifrium.ru в открывшемся браузере, затем нажмите Enter здесь...")

    # URL урока (можно поменять под нужный)
    lesson_url = "https://kb.cifrium.ru/courses/1061/lessons/11602"

    classwork_url = goto_tasks_from_lesson(driver, lesson_url)
    if not classwork_url:
        print("⚠ Не удалось перейти на страницу classworks. Завершаем.")
        return

    iterate_classwork_pages(driver, df, max_tasks=3)

    print("\n✓ Обработка classworks завершена.")
    input("Нажмите Enter для завершения скрипта...")


if __name__ == "__main__":
    main()

