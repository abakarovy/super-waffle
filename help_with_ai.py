"""
Пример интеграции AI Helper с существующим кодом help.py
Показывает, как добавить AI для автоматического решения тестов
"""

from ai_helper import AIHelper
import json
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC


def load_config():
    """Загрузка конфигурации из config.json"""
    try:
        with open('config.json', 'r', encoding='utf-8') as f:
            return json.load(f)
    except Exception as e:
        print(f"⚠ Ошибка загрузки конфигурации: {e}")
        return {"ai_enabled": False}


def extract_question_text(driver):
    """Извлечение текста вопроса со страницы"""
    try:
        # Ищем текст вопроса в различных возможных местах
        selectors = [
            ".fox-ui__sc-s2fogy-0.fvnFet",  # text вопросы
            ".fox-ui__sc-s2fogy-0.dBqbWf",  # code вопросы
            ".MathContent_content__2a8XE",  # общий селектор
            ".fox-Text"
        ]
        
        for selector in selectors:
            try:
                elements = driver.find_elements(By.CSS_SELECTOR, selector)
                for elem in elements:
                    text = elem.text.strip()
                    if text and len(text) > 10:  # Минимальная длина вопроса
                        return text
            except:
                continue
        
        return None
    except Exception as e:
        print(f"⚠ Ошибка извлечения вопроса: {e}")
        return None


def extract_radio_options(driver):
    """Извлечение вариантов для radio вопросов"""
    try:
        task_form = driver.find_element(By.ID, "taskForm")
        radios = task_form.find_elements(By.CSS_SELECTOR, "input[type='radio']")
        
        options = []
        for radio in radios:
            value = radio.get_attribute("value")
            # Ищем текст рядом с radio
            try:
                parent = radio.find_element(By.XPATH, "./..")
                label = parent.find_element(By.CSS_SELECTOR, ".MathContent_content__2a8XE")
                text = label.text.strip()
                if text:
                    options.append({"value": value, "text": text})
            except:
                continue
        
        return options
    except Exception as e:
        print(f"⚠ Ошибка извлечения radio опций: {e}")
        return []


def extract_checkbox_options(driver):
    """Извлечение вариантов для checkbox вопросов"""
    try:
        task_form = driver.find_element(By.ID, "taskForm")
        checkboxes = task_form.find_elements(By.CSS_SELECTOR, "input[type='checkbox']")
        
        options = []
        for checkbox in checkboxes:
            value = checkbox.get_attribute("value")
            # Ищем текст рядом с checkbox
            try:
                parent = checkbox.find_element(By.XPATH, "./..")
                label = parent.find_element(By.CSS_SELECTOR, ".MathContent_content__2a8XE")
                text = label.text.strip()
                if text:
                    options.append({"value": value, "text": text})
            except:
                continue
        
        return options
    except Exception as e:
        print(f"⚠ Ошибка извлечения checkbox опций: {e}")
        return []


def extract_drag_and_drop_options(driver):
    """Извлечение элементов для drag and drop"""
    try:
        task_form = driver.find_element(By.ID, "taskForm")
        
        # Извлекаем целевые области
        targets = []
        target_areas = task_form.find_elements(By.CSS_SELECTOR, ".LinkTaskRow_linkRowTarget__D79Ny")
        for target in target_areas:
            try:
                span = target.find_element(By.CSS_SELECTOR, ".MathContent_content__2a8XE")
                text = span.text.strip()
                if text:
                    targets.append(text)
            except:
                continue
        
        # Извлекаем перетаскиваемые элементы
        draggables = []
        draggable_elements = task_form.find_elements(By.CSS_SELECTOR, "[draggable='true']")
        for draggable in draggable_elements:
            try:
                # Проверяем, что элемент еще не перемещен
                try:
                    parent = draggable.find_element(By.XPATH, "./ancestor::div[contains(@class, 'LinkTaskRow_linkRowContent__XBn6u')]")
                    continue  # Элемент уже перемещен
                except:
                    pass
                
                span = draggable.find_element(By.CSS_SELECTOR, ".MathContent_content__2a8XE")
                text = span.text.strip()
                if text:
                    draggables.append(text)
            except:
                continue
        
        return {"targets": targets, "draggables": draggables}
    except Exception as e:
        print(f"⚠ Ошибка извлечения drag and drop опций: {e}")
        return {"targets": [], "draggables": []}


def solve_with_ai(driver, task_type, ai_helper):
    """
    Решение задачи с использованием AI
    
    Args:
        driver: Selenium WebDriver
        task_type: Тип задачи (radio, checkbox, drag_and_drop, code, text)
        ai_helper: Экземпляр AIHelper
    
    Returns:
        Ответ от AI или None
    """
    if not ai_helper or not ai_helper.enabled:
        return None
    
    print(f"\n🤖 Используем AI для решения задачи типа '{task_type}'")
    
    # Извлекаем вопрос
    question = extract_question_text(driver)
    if not question:
        print("⚠ Не удалось извлечь текст вопроса")
        return None
    
    print(f"   Вопрос: {question[:100]}...")
    
    # Извлекаем варианты в зависимости от типа
    if task_type == "radio":
        options_data = extract_radio_options(driver)
        if not options_data:
            return None
        
        option_texts = [opt["text"] for opt in options_data]
        answer_text = ai_helper.find_answer(question, option_texts, "radio")
        
        # Находим value для выбранного ответа
        if answer_text:
            for opt in options_data:
                if opt["text"] == answer_text or answer_text in opt["text"]:
                    return opt["value"]
        
        return None
    
    elif task_type == "checkbox":
        options_data = extract_checkbox_options(driver)
        if not options_data:
            return None
        
        option_texts = [opt["text"] for opt in options_data]
        answer_texts = ai_helper.find_answer(question, option_texts, "checkbox")
        
        # Находим values для выбранных ответов
        if answer_texts:
            values = []
            for answer_text in answer_texts:
                for opt in options_data:
                    if opt["text"] == answer_text or answer_text in opt["text"]:
                        values.append(opt["value"])
                        break
            return values if values else None
        
        return None
    
    elif task_type == "drag_and_drop":
        options = extract_drag_and_drop_options(driver)
        if not options["targets"] or not options["draggables"]:
            return None
        
        mapping = ai_helper.find_answer(question, options, "drag_and_drop")
        return mapping
    
    elif task_type == "code":
        code = ai_helper.find_answer(question, [], "code")
        return code
    
    elif task_type == "text":
        answer = ai_helper.find_answer(question, [], "text")
        return answer
    
    return None


def example_usage():
    """Пример использования AI интеграции"""
    
    # Загружаем конфигурацию
    config = load_config()
    
    # Инициализируем AI Helper
    ai_helper = None
    if config.get("ai_enabled"):
        ai_helper = AIHelper(
            api_key=config.get("ai_api_key"),
            model=config.get("ai_model")
        )
        
        if ai_helper.enabled:
            print("✓ AI Helper активирован")
        else:
            print("⚠ AI Helper не активирован")
            ai_helper = None
    else:
        print("ℹ AI отключен в конфигурации")
    
    # Пример интеграции с существующим кодом
    # В вашем коде help.py, после определения типа задачи:
    
    """
    # В функции detect_task_type() после определения типа:
    task_type = detect_task_type(driver)
    
    # Пробуем решить с помощью AI
    if ai_helper and config.get("use_ai_for_tests", True):
        ai_answer = solve_with_ai(driver, task_type, ai_helper)
        
        if ai_answer:
            print(f"✓ AI нашел ответ!")
            
            # Используем ответ в зависимости от типа
            if task_type == "radio":
                success = handle_radio_task(driver, ai_answer)
            elif task_type == "checkbox":
                success = handle_checkbox_task(driver, ai_answer)
            elif task_type == "drag_and_drop":
                success = handle_drag_and_drop_task(driver, ai_answer)
            elif task_type == "code":
                success = handle_code_task(driver, ai_answer)
            elif task_type == "text":
                success = handle_text_task(driver, ai_answer)
            
            if success:
                print("✓ Ответ успешно применен")
            else:
                print("⚠ Не удалось применить ответ")
                if config.get("fallback_to_manual", True):
                    print("ℹ Переключаемся на ручной режим")
                    # Здесь ваш код для ручного ввода из Excel
        else:
            print("⚠ AI не смог найти ответ")
            if config.get("fallback_to_manual", True):
                print("ℹ Используем данные из Excel")
                # Здесь ваш код для ручного ввода из Excel
    else:
        # AI отключен, используем данные из Excel
        print("ℹ Используем данные из Excel")
        # Здесь ваш код для ручного ввода из Excel
    """
    
    print("\n" + "="*50)
    print("Пример интеграции готов!")
    print("Скопируйте код выше в ваш help.py")
    print("="*50)


if __name__ == "__main__":
    example_usage()
