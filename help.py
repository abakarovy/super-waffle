from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.action_chains import ActionChains
import time
import os
import sys
import subprocess
import signal
import re
import pandas as pd
import json
import requests

# Глобальная переменная для driver, чтобы можно было закрыть его при Ctrl+C
global_driver = None

# URL главной страницы
MAIN_PAGE_URL_1 = "https://kb.cifrium.ru/teacher/courses/770"  # Модуль 1
MAIN_PAGE_URL = "https://kb.cifrium.ru/teacher/courses/771"  # Модуль 2
MAIN_PAGE_URL_2 = "https://kb.cifrium.ru/teacher/courses/772"  # Модуль 3
HOME_URL = "https://kb.cifrium.ru/"
LOGIN_URL = "https://kb.cifrium.ru/user/login"

# OpenRouter API настройки
OPENROUTER_API_KEY = "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"  # Можно установить через переменную окружения
OPENROUTER_MODEL = "anthropic/claude-3.5-sonnet"  # Модель по умолчанию
OPENROUTER_API_URL = "https://openrouter.ai/api/v1/chat/completions"

def setup_driver():
    """Настройка и создание драйвера Chrome (без профиля)"""
    print("Настраиваем Chrome драйвер...")
    chrome_options = Options()
    
    # Простые опции без профиля
    chrome_options.add_argument("--disable-dev-shm-usage")
    chrome_options.add_argument("--disable-gpu")
    chrome_options.add_argument("--no-sandbox")
    chrome_options.add_argument("--disable-infobars")
    chrome_options.add_argument("--disable-blink-features=AutomationControlled")
    chrome_options.add_experimental_option("excludeSwitches", ["enable-automation"])
    chrome_options.add_experimental_option('useAutomationExtension', False)
    
    # Отвязываем браузер от процесса драйвера, чтобы он оставался открытым после завершения скрипта
    chrome_options.add_experimental_option("detach", True)
    
    print("Создаем экземпляр браузера...")
    try:
        driver = webdriver.Chrome(options=chrome_options)
        print("✓ Браузер успешно открыт!")
        driver.maximize_window()
        return driver
    except Exception as e:
        print(f"\n✗ ОШИБКА при создании браузера: {e}")
        import traceback
        traceback.print_exc()
        raise

def find_lessons_list(driver):
    """Находит список заданий по частичному совпадению класса"""
    wait = WebDriverWait(driver, 10)
    
    # Ищем элемент с классом, начинающимся с "lessons-list__List-"
    # Используем XPath для поиска по частичному совпадению
    try:
        lessons_list = wait.until(
            EC.presence_of_element_located((
                By.XPATH, 
                "//div[contains(@class, 'lessons-list__List-')]"
            ))
        )
        return lessons_list
    except Exception as e:
        print(f"Ошибка при поиске списка заданий: {e}")
        return None

def get_task_links(driver, lessons_list, course_id="771"):
    """Извлекает все ссылки на задания из списка
    course_id - ID курса (по умолчанию 771)"""
    try:
        # Находим все элементы <a> внутри списка заданий
        task_links = lessons_list.find_elements(By.TAG_NAME, "a")
        
        links = []
        for link in task_links:
            href = link.get_attribute("href")
            if href and f"/teacher/courses/{course_id}/lessons/" in href:
                # Проверяем, выполнено ли задание
                is_completed = check_if_completed(link)
                links.append({
                    "href": href,
                    "completed": is_completed,
                    "element": link
                })
        
        return links
    except Exception as e:
        print(f"Ошибка при извлечении ссылок: {e}")
        return []

def check_if_completed(link_element):
    """Проверяет, выполнено ли задание по количеству решенных задач на странице курса
    Ищет Item_tasks__[random] внутри Item_right__[random] или Item__right__[random]
    Проверяет формат "Решено задач: x / n" или "x / n"
    Задание считается выполненным только если все задачи решены (x >= n)"""
    try:
        # Ищем Item_right__[random] или Item__right__[random] (может быть разный формат)
        # В HTML может быть: Item_right__LZdFn или Item__right__[random]
        right_div = None
        try:
            # Пробуем сначала с одним подчеркиванием (Item_right__)
            right_div = link_element.find_element(
                By.XPATH,
                ".//div[contains(@class, 'Item_right__')]"
            )
        except:
            try:
                # Пробуем с двумя подчеркиваниями (Item__right__)
                right_div = link_element.find_element(
                    By.XPATH,
                    ".//div[contains(@class, 'Item__right__')]"
                )
            except:
                # Пробуем альтернативный способ поиска
                try:
                    right_div = link_element.find_element(
                        By.XPATH,
                        ".//div[contains(@class, 'Item_right')]"
                    )
                except:
                    pass
        
        if not right_div:
            return False
        
        # Ищем Item_tasks__[random] внутри right_div
        tasks_div = None
        try:
            tasks_div = right_div.find_element(
                By.XPATH, 
                ".//div[contains(@class, 'Item_tasks__')]"
            )
        except:
            pass
        
        if not tasks_div:
            return False
        
        # Получаем текст
        tasks_text = tasks_div.text.strip()
        
        # Парсим текст - может быть "Решено задач: x / n" или "x / n"
        # Ищем паттерн "число / число" в тексте (поддерживаем оба формата)
        match = re.search(r'(\d+)\s*/\s*(\d+)', tasks_text)
        
        if match:
            solved_count = int(match.group(1))  # Первое число (решенные задачи)
            total_count = int(match.group(2))   # Второе число (всего задач)
            
            # Задание считается выполненным только если все задачи решены
            return solved_count >= total_count
        else:
            # Если не удалось распарсить, считаем невыполненным
            return False
            
    except Exception as e:
        # Если не нашли элементы, считаем задание невыполненным
        return False

def find_load_more_button(driver, lessons_list):
    """Находит кнопку 'Показать ещё' и возвращает её, если она существует и не disabled"""
    try:
        load_more_button = None
        
        # Способ 1: Ищем как следующий sibling элемента списка
        try:
            load_more_button = lessons_list.find_element(
                By.XPATH,
                "./following-sibling::div[contains(@class, 'LoadMore_root__')]"
            )
        except:
            pass
        
        # Способ 2: Ищем в родительском элементе
        if not load_more_button:
            try:
                parent = lessons_list.find_element(By.XPATH, "./..")
                load_more_button = parent.find_element(
                    By.XPATH,
                    ".//div[contains(@class, 'LoadMore_root__')]"
                )
            except:
                pass
        
        # Способ 3: Ищем на всей странице
        if not load_more_button:
            try:
                load_more_button = driver.find_element(
                    By.XPATH,
                    "//div[contains(@class, 'LoadMore_root__')]"
                )
            except:
                pass
        
        # Если кнопка не найдена, возвращаем None
        if not load_more_button:
            return None
        
        # Проверяем, есть ли класс LoadMore_disabled__
        button_classes = load_more_button.get_attribute("class")
        if button_classes and "LoadMore_disabled__" in button_classes:
            return None  # Кнопка disabled, возвращаем None
        
        return load_more_button
        
    except Exception as e:
        return None

def click_load_more_button(driver, load_more_button):
    """Нажимает на кнопку 'Показать ещё'"""
    try:
        # Прокручиваем к кнопке, чтобы она была видима
        driver.execute_script("arguments[0].scrollIntoView({block: 'center'});", load_more_button)
        time.sleep(0.5)
        
        # Пробуем обычный клик
        try:
            load_more_button.click()
        except:
            # Если обычный клик не работает, используем JavaScript
            driver.execute_script("arguments[0].click();", load_more_button)
        
        # Ждем загрузки новых заданий
        time.sleep(2)
        return True
    except Exception as e:
        print(f"  ⚠ Ошибка при нажатии на кнопку: {e}")
        return False

def handle_homework_button(driver):
    """Ищет кнопку с классом WebinarCourseHomeworkBlock и кликает на неё, или переходит на tasks страницу"""
    try:
        wait = WebDriverWait(driver, 5)
        
        # Пробуем найти кнопку по ID или классу
        homework_button = None
        
        # Способ 1: Поиск по ID
        try:
            homework_button = driver.find_element(By.ID, "WebinarCourseHomeworkBlock")
            print("  Найдена кнопка 'Решить задачи' по ID")
        except:
            pass
        
        # Способ 2: Поиск по классу (частичное совпадение)
        if not homework_button:
            try:
                homework_button = driver.find_element(
                    By.XPATH,
                    "//div[contains(@class, 'WebinarCourseHomeworkBlock')]"
                )
                print("  Найдена кнопка 'Решить задачи' по классу")
            except:
                pass
        
        # Способ 3: Поиск по тексту кнопки
        if not homework_button:
            try:
                homework_button = driver.find_element(
                    By.XPATH,
                    "//div[contains(text(), 'Решить задачи к занятию')]"
                )
                print("  Найдена кнопка 'Решить задачи' по тексту")
            except:
                pass
        
        if homework_button:
            print("  Кликаем на кнопку 'Решить задачи'...")
            try:
                # Прокручиваем к кнопке
                driver.execute_script("arguments[0].scrollIntoView({block: 'center'});", homework_button)
                time.sleep(0.5)
                
                # Кликаем на кнопку
                try:
                    homework_button.click()
                except:
                    driver.execute_script("arguments[0].click();", homework_button)
                
                print("  ✓ Кнопка нажата")
                time.sleep(2)  # Ждем перехода
                
                # Проверяем, есть ли кнопка "Продолжить тест" (для контрольных заданий)
                handle_continue_test_button(driver)
                
                return True
            except Exception as click_error:
                print(f"  ⚠ Ошибка при клике на кнопку: {click_error}")
                # Пробуем перейти на tasks страницу
                return go_to_tasks_page(driver)
        else:
            print("  Кнопка 'Решить задачи' не найдена, переходим на tasks страницу...")
            return go_to_tasks_page(driver)
            
    except Exception as e:
        print(f"  ⚠ Ошибка при поиске кнопки: {e}")
        return go_to_tasks_page(driver)

def handle_continue_test_button(driver):
    """Ищет и нажимает кнопку 'Продолжить тест' на странице контрольных заданий"""
    try:
        wait = WebDriverWait(driver, 5)
        
        # Пробуем найти кнопку по ID
        continue_button = None
        try:
            continue_button = driver.find_element(By.ID, "training-main-page-btn")
            print("  Найдена кнопка 'Продолжить тест' по ID")
        except:
            pass
        
        # Пробуем найти кнопку по классу
        if not continue_button:
            try:
                continue_button = driver.find_element(
                    By.CSS_SELECTOR,
                    "button.fox-Button.Actions_actionButton__SiPlS"
                )
                print("  Найдена кнопка 'Продолжить тест' по классу")
            except:
                pass
        
        # Пробуем найти кнопку по тексту
        if not continue_button:
            try:
                continue_button = driver.find_element(
                    By.XPATH,
                    "//button[contains(@class, 'fox-Button') and .//span[contains(text(), 'Продолжить тест')]]"
                )
                print("  Найдена кнопка 'Продолжить тест' по тексту")
            except:
                pass
        
        if continue_button:
            print("  Кликаем на кнопку 'Продолжить тест'...")
            try:
                # Прокручиваем к кнопке
                driver.execute_script("arguments[0].scrollIntoView({block: 'center'});", continue_button)
                time.sleep(0.5)
                
                # Кликаем на кнопку
                try:
                    continue_button.click()
                except:
                    driver.execute_script("arguments[0].click();", continue_button)
                
                print("  ✓ Кнопка 'Продолжить тест' нажата")
                time.sleep(2)  # Ждем перехода на страницу с задачами
                return True
            except Exception as click_error:
                print(f"  ⚠ Ошибка при клике на кнопку 'Продолжить тест': {click_error}")
                return False
        else:
            print("  Кнопка 'Продолжить тест' не найдена (возможно, это не контрольное задание)")
            return False
            
    except Exception as e:
        print(f"  ⚠ Ошибка при поиске кнопки 'Продолжить тест': {e}")
        return False

def go_to_tasks_page(driver):
    """Переходит на страницу tasks для текущего урока"""
    try:
        current_url = driver.current_url
        print(f"  Текущий URL: {current_url}")
        
        # Извлекаем lessonid из текущего URL
        # URL может быть вида: https://kb.cifrium.ru/teacher/courses/771/lessons/[lessonid]
        match = re.search(r'/lessons/(\d+)', current_url)
        
        if match:
            lesson_id = match.group(1)
            tasks_url = f"https://kb.cifrium.ru/teacher/lessons/{lesson_id}/tasks"
            print(f"  Переходим на страницу задач: {tasks_url}")
            driver.get(tasks_url)
            time.sleep(2)
            print("  ✓ Перешли на страницу задач")
            
            # Проверяем, есть ли кнопка "Продолжить тест" (для контрольных заданий)
            handle_continue_test_button(driver)
            
            return True
        else:
            print("  ⚠ Не удалось извлечь lesson ID из URL")
            return False
            
    except Exception as e:
        print(f"  ⚠ Ошибка при переходе на tasks страницу: {e}")
        return False

def get_task_form(driver, timeout=3):
    """Получает форму задачи с ожиданием загрузки
    Поддерживает как обычные формы (ID="taskForm"), так и контрольные задания (action="/trainings/...")"""
    wait = WebDriverWait(driver, timeout)
    
    # Сначала пробуем найти форму по ID (обычные задания)
    try:
        form = wait.until(EC.presence_of_element_located((By.ID, "taskForm")))
        return form
    except:
        pass
    
    # Если не найдено, пробуем найти форму контрольного задания (action="/trainings/...")
    try:
        form = wait.until(EC.presence_of_element_located((By.XPATH, "//form[contains(@action, '/trainings/')]")))
        print("  Найдена форма контрольного задания")
        return form
    except:
        pass
    
    # Если все еще не найдено, пробуем найти любую форму с кнопкой отправки
    try:
        form = wait.until(EC.presence_of_element_located((By.XPATH, "//form[.//button[@type='submit']]")))
        print("  Найдена форма по наличию кнопки submit")
        return form
    except:
        pass
    
    # Последняя попытка: найти форму с классом wkUtils_userUnselectable__tdz2n (контрольные задания)
    try:
        form = wait.until(EC.presence_of_element_located((By.CSS_SELECTOR, "form.wkUtils_userUnselectable__tdz2n")))
        print("  Найдена форма контрольного задания по классу")
        return form
    except:
        pass
    
    # Если ничего не найдено, возвращаем ошибку
    raise Exception("Не удалось найти форму задачи")

def detect_task_type(driver):
    """Определяет тип задачи на странице"""
    try:
        # Ждем загрузки формы задачи
        print("  Ожидаем загрузки формы задачи...")
        task_form = get_task_form(driver)
        print("  Форма задачи загружена")
        
        # Проверяем, является ли задача уже решенной (наличие элементов Solved_block)
        # Это должно быть первой проверкой, так как HTML меняется для решенных задач
        try:
            # Проверяем различные варианты классов для решенных задач
            solved_selectors = [
                ".Solved_block__+9eqO",
                "[class*='Solved_block']",
                "[class*='Solved_column']",
                "[class*='Solved_input']",
                "[class*='Solved_user']",
                "[class*='Solved_correct']",
                ".Solved_input__CZlOd",
                ".Solved_column__XCV8c"
            ]
            
            for selector in solved_selectors:
                try:
                    solved_elements = task_form.find_elements(By.CSS_SELECTOR, selector)
                    if solved_elements:
                        print(f"  ✓ Задача уже решена (найдены элементы Solved: {selector})")
                        return "solved"
                except:
                    continue
            
            # Дополнительная проверка: ищем текст "Правильный ответ:" или "Ваш ответ:"
            try:
                solved_text = task_form.find_elements(By.XPATH, ".//*[contains(text(), 'Правильный ответ:') or contains(text(), 'Ваш ответ:')]")
                if solved_text:
                    print("  ✓ Задача уже решена (найден текст 'Правильный ответ' или 'Ваш ответ')")
                    return "solved"
            except:
                pass
                
        except Exception as e:
            # Игнорируем ошибки при проверке
            pass
        
        # Проверяем наличие различных элементов для определения типа
        
        # 1. Checkbox - множественный выбор
        try:
            checkboxes = task_form.find_elements(By.CSS_SELECTOR, "input[type='checkbox']")
            if checkboxes:
                print("  Тип задачи: CHECKBOX (множественный выбор)")
                return "checkbox"
        except:
            pass
        
        # 2. Radio - одиночный выбор (только если нет checkbox)
        try:
            radios = task_form.find_elements(By.CSS_SELECTOR, "input[type='radio']")
            if radios:
                # Проверяем, нет ли checkbox - если есть, приоритет у checkbox
                checkboxes = task_form.find_elements(By.CSS_SELECTOR, "input[type='checkbox']")
                if not checkboxes:
                    print("  Тип задачи: RADIO (одиночный выбор)")
                    return "radio"
        except:
            pass
        
        # 3. Drag and drop - перетаскивание
        try:
            draggable = task_form.find_elements(By.CSS_SELECTOR, "[draggable='true']")
            link_rows = task_form.find_elements(By.CSS_SELECTOR, ".LinkTaskRow_linkRow__36TU1")
            if draggable and link_rows:
                # Проверяем, является ли это multi-use drag and drop (LinkTask)
                # В multi-use типе элементы остаются в панели опций после перетаскивания
                try:
                    # Проверяем наличие панели опций LinkTask
                    link_options_panel = task_form.find_elements(By.CSS_SELECTOR, ".LinkTask_optionsPanel__GLzIR")
                    # Проверяем описание, которое указывает на multi-use
                    description_text = task_form.find_elements(By.XPATH, ".//*[contains(text(), 'каждый может быть использован несколько раз') or contains(text(), 'может быть использован несколько раз')]")
                    if link_options_panel or description_text:
                        print("  Тип задачи: DRAG_AND_DROP (multi-use перетаскивание - элементы остаются в панели)")
                        return "drag_and_drop"  # Используем тот же тип, но обрабатываем по-другому
                    else:
                        print("  Тип задачи: DRAG_AND_DROP (обычное перетаскивание)")
                        return "drag_and_drop"
                except:
                    print("  Тип задачи: DRAG_AND_DROP (перетаскивание)")
                    return "drag_and_drop"
        except:
            pass
        
        # 4. Code - написание кода
        try:
            # Проверяем наличие textarea с source_code
            code_textarea = task_form.find_element(By.CSS_SELECTOR, "textarea[name*='source_code']")
            if code_textarea:
                print("  Тип задачи: CODE (написание кода) - найден textarea")
                return "code"
        except:
            pass
        
        # Проверяем наличие CodeMirror редактора (новый формат)
        try:
            # Ищем панель Main с CodeMirror редактором
            main_panel = task_form.find_element(By.XPATH, ".//div[contains(@class, 'styled__PanelHeader') and contains(text(), 'Main')]/following-sibling::div[contains(@class, 'styled__PanelContent')]")
            cm_editor = main_panel.find_element(By.CSS_SELECTOR, ".cm-editor")
            if cm_editor:
                print("  Тип задачи: CODE (написание кода) - найден CodeMirror в панели Main")
                return "code"
        except:
            pass
        
        # Альтернативная проверка: ищем любой CodeMirror редактор с data-language
        try:
            cm_editor = task_form.find_element(By.CSS_SELECTOR, ".cm-editor[data-language]")
            if cm_editor:
                print("  Тип задачи: CODE (написание кода) - найден CodeMirror с data-language")
                return "code"
        except:
            pass
        
        # Самая общая проверка: ищем любой CodeMirror редактор (без дополнительных условий)
        try:
            cm_editor = task_form.find_element(By.CSS_SELECTOR, ".cm-editor")
            if cm_editor:
                print("  Тип задачи: CODE (написание кода) - найден CodeMirror редактор")
                return "code"
        except:
            pass
        
        # Проверка по наличию контейнера редактора кода или кнопок запуска кода
        try:
            # Ищем контейнеры, которые обычно содержат редактор кода
            code_container = task_form.find_elements(By.CSS_SELECTOR, ".CodeEditor_root, .CodeEditor_container, [class*='CodeEditor'], [class*='CodeMirror']")
            if code_container:
                print("  Тип задачи: CODE (написание кода) - найден контейнер редактора кода")
                return "code"
        except:
            pass
        
        # Дополнительная проверка: ищем CodeMirror в документе целиком (не только в форме)
        try:
            cm_editor = driver.find_element(By.CSS_SELECTOR, ".cm-editor")
            if cm_editor:
                print("  Тип задачи: CODE (написание кода) - найден CodeMirror редактор в документе")
                return "code"
        except:
            pass
        
        # Отладочная информация: выводим что было найдено
        try:
            print(f"  [DEBUG] Проверка элементов для определения типа задачи:")
            print(f"    - Checkboxes: {len(task_form.find_elements(By.CSS_SELECTOR, 'input[type=\"checkbox\"]'))}")
            print(f"    - Radios: {len(task_form.find_elements(By.CSS_SELECTOR, 'input[type=\"radio\"]'))}")
            print(f"    - Draggable: {len(task_form.find_elements(By.CSS_SELECTOR, '[draggable=\"true\"]'))}")
            print(f"    - Link rows: {len(task_form.find_elements(By.CSS_SELECTOR, '.LinkTaskRow_linkRow__36TU1'))}")
            print(f"    - CodeMirror в форме: {len(task_form.find_elements(By.CSS_SELECTOR, '.cm-editor'))}")
            print(f"    - CodeMirror в документе: {len(driver.find_elements(By.CSS_SELECTOR, '.cm-editor'))}")
            print(f"    - Textarea с source_code: {len(task_form.find_elements(By.CSS_SELECTOR, 'textarea[name*=\"source_code\"]'))}")
        except:
            pass
        
        # 5. Text - текстовый ввод
        try:
            text_input = task_form.find_element(By.CSS_SELECTOR, "input[type='text'][name*='questions']")
            if text_input:
                print("  Тип задачи: TEXT (текстовый ввод)")
                return "text"
        except:
            pass
        
        print("  ⚠ Не удалось определить тип задачи")
        return "unknown"
        
    except Exception as e:
        print(f"  ⚠ Ошибка при определении типа задачи: {e}")
        return "unknown"

def handle_checkbox_task(driver, answers):
    """Обрабатывает задачу типа checkbox (множественный выбор)
    answers - список значений (value) для выбора"""
    try:
        task_form = get_task_form(driver)
        checkboxes = task_form.find_elements(By.CSS_SELECTOR, "input[type='checkbox']")
        
        print(f"  Найдено чекбоксов: {len(checkboxes)}")
        print(f"  Выбираем значения: {answers}")
        
        selected_count = 0
        for checkbox in checkboxes:
            value = checkbox.get_attribute("value")
            if value in answers:
                # Прокручиваем к чекбоксу
                driver.execute_script("arguments[0].scrollIntoView({block: 'center'});", checkbox)
                time.sleep(0.3)
                
                # Проверяем, не выбран ли уже
                if checkbox.is_selected():
                    print(f"    Чекбокс со значением {value} уже выбран")
                    selected_count += 1
                    continue
                
                # Пробуем несколько способов выбора
                success = False
                
                # Способ 1: Клик на label или родительский элемент
                try:
                    # Ищем label, связанный с чекбоксом
                    label = None
                    try:
                        label_id = checkbox.get_attribute("id")
                        if label_id:
                            label = task_form.find_element(By.CSS_SELECTOR, f"label[for='{label_id}']")
                    except:
                        pass
                    
                    # Если label не найден, ищем родительский элемент с текстом
                    if not label:
                        try:
                            parent = checkbox.find_element(By.XPATH, "./..")
                            # Кликаем на родительский элемент
                            driver.execute_script("arguments[0].scrollIntoView({block: 'center'});", parent)
                            time.sleep(0.2)
                            parent.click()
                            time.sleep(0.2)
                            if checkbox.is_selected():
                                success = True
                                print(f"    ✓ Выбран чекбокс со значением: {value} (через родительский элемент)")
                        except:
                            pass
                    
                    # Если нашли label, кликаем на него
                    if not success and label:
                        driver.execute_script("arguments[0].scrollIntoView({block: 'center'});", label)
                        time.sleep(0.2)
                        label.click()
                        time.sleep(0.2)
                        if checkbox.is_selected():
                            success = True
                            print(f"    ✓ Выбран чекбокс со значением: {value} (через label)")
                except Exception as e:
                    print(f"    ⚠ Ошибка при клике на label/parent: {e}")
                
                # Способ 2: Прямой клик на чекбокс
                if not success:
                    try:
                        checkbox.click()
                        time.sleep(0.2)
                        if checkbox.is_selected():
                            success = True
                            print(f"    ✓ Выбран чекбокс со значением: {value} (прямой клик)")
                    except Exception as e:
                        print(f"    ⚠ Ошибка при прямом клике: {e}")
                
                # Способ 3: JavaScript с полными событиями
                if not success:
                    try:
                        driver.execute_script("""
                            var checkbox = arguments[0];
                            checkbox.checked = true;
                            
                            // Триггерим все необходимые события
                            var events = ['click', 'change', 'input'];
                            events.forEach(function(eventType) {
                                var event = new Event(eventType, { bubbles: true, cancelable: true });
                                checkbox.dispatchEvent(event);
                            });
                            
                            // Также пробуем через MouseEvent
                            var mouseEvent = new MouseEvent('click', {
                                bubbles: true,
                                cancelable: true,
                                view: window
                            });
                            checkbox.dispatchEvent(mouseEvent);
                        """, checkbox)
                        time.sleep(0.3)
                        if checkbox.is_selected():
                            success = True
                            print(f"    ✓ Выбран чекбокс со значением: {value} (через JS события)")
                    except Exception as e:
                        print(f"    ⚠ Ошибка при JS установке: {e}")
                
                if success:
                    selected_count += 1
                else:
                    print(f"    ⚠ Не удалось выбрать чекбокс со значением: {value}")
        
        print(f"  ✓ Выбрано чекбоксов: {selected_count} из {len(answers)}")
        return selected_count > 0
        
    except Exception as e:
        print(f"  ⚠ Ошибка при обработке checkbox задачи: {e}")
        return False

def handle_radio_task(driver, answer):
    """Обрабатывает задачу типа radio (одиночный выбор)
    answer - значение (value) для выбора или текст ответа"""
    try:
        task_form = get_task_form(driver)
        radios = task_form.find_elements(By.CSS_SELECTOR, "input[type='radio']")
        
        print(f"  Найдено радио-кнопок: {len(radios)}")
        print(f"  Выбираем значение: {answer}")
        
        # Сначала пробуем найти по значению (value)
        for radio in radios:
            value = radio.get_attribute("value")
            if str(value) == str(answer):
                # Прокручиваем к радио-кнопке
                driver.execute_script("arguments[0].scrollIntoView({block: 'center'});", radio)
                time.sleep(0.3)
                
                # Кликаем на радио-кнопку
                try:
                    # Сначала пробуем через JavaScript (более надежно)
                    driver.execute_script("""
                        var radio = arguments[0];
                        // Устанавливаем checked
                        radio.checked = true;
                        
                        // Инициируем события
                        var changeEvent = new Event('change', { bubbles: true, cancelable: true });
                        radio.dispatchEvent(changeEvent);
                        
                        var clickEvent = new Event('click', { bubbles: true, cancelable: true });
                        radio.dispatchEvent(clickEvent);
                        
                        // Также пробуем кликнуть на родительский элемент (для контрольных заданий)
                        var parent = radio.closest('div[class*="styled__Root"]');
                        if (parent) {
                            parent.click();
                        }
                    """, radio)
                    
                    # Проверяем, что радио-кнопка выбрана
                    time.sleep(0.3)
                    is_selected = driver.execute_script("return arguments[0].checked;", radio)
                    
                    if is_selected:
                        print(f"    ✓ Радио-кнопка со значением {value} успешно выбрана через JS")
                        return True
                    else:
                        # Если JavaScript не сработал, пробуем обычный клик
                        print(f"    ⚠ Радио-кнопка не выбрана через JS, пробуем обычный клик...")
                        try:
                            # Ищем родительский div с классом styled__Root (для контрольных заданий)
                            parent = radio.find_element(By.XPATH, "./ancestor::div[contains(@class, 'styled__Root')][1]")
                            parent.click()
                            print(f"    ✓ Кликнули на родительский элемент радио-кнопки")
                        except:
                            radio.click()
                            print(f"    ✓ Кликнули на радио-кнопку напрямую")
                        
                        time.sleep(0.2)
                        is_selected = radio.is_selected()
                        if is_selected:
                            print(f"    ✓ Радио-кнопка со значением {value} успешно выбрана")
                            return True
                        else:
                            print(f"    ⚠ Радио-кнопка все еще не выбрана")
                            return False
                except Exception as e:
                    print(f"    ⚠ Ошибка при клике: {e}, пробуем через JavaScript...")
                    # Если прямой клик не работает, пробуем через JavaScript
                    try:
                        driver.execute_script("arguments[0].checked = true;", radio)
                        driver.execute_script("arguments[0].dispatchEvent(new Event('change'));", radio)
                        driver.execute_script("arguments[0].dispatchEvent(new Event('click'));", radio)
                        time.sleep(0.2)
                        is_selected = driver.execute_script("return arguments[0].checked;", radio)
                        if is_selected:
                            print(f"    ✓ Радио-кнопка со значением {value} выбрана через JS")
                            return True
                        else:
                            print(f"    ⚠ Радио-кнопка не выбрана даже через JS")
                            return False
                    except Exception as js_e:
                        print(f"    ⚠ Ошибка при выборе через JS: {js_e}")
                        return False
        
        # Если не найдено по значению, пробуем найти по тексту (для контрольных заданий)
        print(f"  Не найдено по значению, ищем по тексту ответа...")
        radio_match, value_match = find_best_radio_match(str(answer), radios)
        if radio_match and value_match:
            print(f"  Найдено совпадение по тексту, выбираем радио-кнопку со значением: {value_match}")
            # Используем тот же код для выбора
            radio = radio_match
            value = value_match
            
            # Прокручиваем к радио-кнопке
            driver.execute_script("arguments[0].scrollIntoView({block: 'center'});", radio)
            time.sleep(0.3)
            
            # Кликаем на радио-кнопку
            try:
                # Сначала пробуем через JavaScript
                driver.execute_script("""
                    var radio = arguments[0];
                    radio.checked = true;
                    var changeEvent = new Event('change', { bubbles: true, cancelable: true });
                    radio.dispatchEvent(changeEvent);
                    var clickEvent = new Event('click', { bubbles: true, cancelable: true });
                    radio.dispatchEvent(clickEvent);
                    var parent = radio.closest('div[class*="styled__Root"]');
                    if (parent) {
                        parent.click();
                    }
                """, radio)
                
                time.sleep(0.3)
                is_selected = driver.execute_script("return arguments[0].checked;", radio)
                
                if is_selected:
                    print(f"    ✓ Радио-кнопка со значением {value} успешно выбрана через JS")
                    return True
                else:
                    # Пробуем кликнуть на родительский элемент
                    try:
                        parent = radio.find_element(By.XPATH, "./ancestor::div[contains(@class, 'styled__Root')][1]")
                        parent.click()
                        print(f"    ✓ Кликнули на родительский элемент")
                    except:
                        radio.click()
                    
                    time.sleep(0.2)
                    is_selected = radio.is_selected()
                    if is_selected:
                        print(f"    ✓ Радио-кнопка со значением {value} успешно выбрана")
                        return True
            except Exception as e:
                print(f"    ⚠ Ошибка при выборе: {e}")
                return False
        
        print(f"  ⚠ Не найдена радио-кнопка для ответа: {answer}")
        return False
        
    except Exception as e:
        print(f"  ⚠ Ошибка при обработке radio задачи: {e}")
        import traceback
        traceback.print_exc()
        return False

def handle_drag_and_drop_task(driver, mappings):
    """Обрабатывает задачу типа drag and drop (перетаскивание)
    mappings - словарь {текст_цели: текст_элемента} или список кортежей [(текст_цели, текст_элемента)]
    Поддерживает три типа:
    1. Текстовые элементы - сопоставление по тексту
    2. Изображения - сопоставление по индексу (element_text должен быть числом или строкой с числом)
    3. Multi-use drag and drop - элементы остаются в панели опций и могут использоваться несколько раз"""
    try:
        task_form = get_task_form(driver)
        
        # Определяем, является ли это multi-use drag and drop
        is_multi_use = False
        try:
            link_options_panel = task_form.find_elements(By.CSS_SELECTOR, ".LinkTask_optionsPanel__GLzIR")
            description_text = task_form.find_elements(By.XPATH, ".//*[contains(text(), 'каждый может быть использован несколько раз') or contains(text(), 'может быть использован несколько раз')]")
            if link_options_panel or description_text:
                is_multi_use = True
                print("  [DEBUG] Обнаружен multi-use drag and drop - элементы остаются в панели опций")
        except:
            pass
        
        # Находим все перетаскиваемые элементы
        draggable_elements = task_form.find_elements(By.CSS_SELECTOR, "[draggable='true']")
        print(f"  Найдено перетаскиваемых элементов: {len(draggable_elements)}")
        
        # Проверяем, есть ли изображения в draggable элементах
        has_images = False
        initial_image_order = []  # Сохраняем исходный порядок изображений для сопоставления по индексу
        
        for draggable in draggable_elements[:3]:  # Проверяем первые 3 элемента
            try:
                # Проверяем наличие изображения
                image_content = draggable.find_element(By.CSS_SELECTOR, ".styled__ImageContent-eNVTVI, .styled__ImageContent")
                has_images = True
                print("  Обнаружены изображения в draggable элементах - используем сопоставление по индексу")
                break
            except:
                continue
        
        # Если это изображения, сохраняем исходный порядок всех изображений
        # Вместо сохранения самих элементов сохраняем их идентификаторы для избежания stale element reference
        if has_images:
            try:
                # Используем JavaScript для получения стабильных идентификаторов изображений
                image_info = driver.execute_script("""
                    var optionsPanel = arguments[0];
                    var imageOptions = optionsPanel.querySelectorAll('.OptionsSlide_image__nlliP, .styled__ImageOption-ftJQiu, [draggable="true"]');
                    var identifiers = [];
                    var imageDetails = [];
                    
                    for (var i = 0; i < imageOptions.length; i++) {
                        var option = imageOptions[i];
                        // Проверяем наличие изображения
                        var hasImage = option.querySelector('.styled__ImageContent-eNVTVI, .styled__ImageContent');
                        if (hasImage || option.getAttribute('draggable') === 'true') {
                            // Находим draggable элемент
                            var draggable = option.querySelector('[draggable="true"]') || option;
                            // Сохраняем индекс в исходном порядке
                            identifiers.push(i);
                            
                            // Сохраняем детали для отладки
                            var imageContent = option.querySelector('.styled__ImageContent-eNVTVI, .styled__ImageContent');
                            var imageClass = imageContent ? imageContent.className : '';
                            var imageSrc = imageContent ? (imageContent.src || imageContent.getAttribute('src') || imageContent.style.backgroundImage || '') : '';
                            imageDetails.push({
                                index: i + 1,
                                className: imageClass,
                                src: imageSrc.substring(0, 50) // Первые 50 символов для отладки
                            });
                        }
                    }
                    
                    return {identifiers: identifiers, details: imageDetails};
                """, task_form.find_element(By.CSS_SELECTOR, ".Options_root__q5QuO, .Options_optionsRows__JttWG, .LinkTask_optionsPanel__GLzIR"))
                
                initial_image_order = image_info['identifiers']
                image_details = image_info['details']
                print(f"  [DEBUG] Сохранен исходный порядок изображений: {len(initial_image_order)} элементов")
                print(f"  [DEBUG] Порядок изображений в панели опций (слева направо, сверху вниз):")
                for detail in image_details:
                    className = detail.get('className', 'N/A')
                    print(f"    {detail['index']}. className: {className}, src: {detail['src']}")
            except Exception as e:
                print(f"  [DEBUG] Ошибка при сохранении порядка изображений: {e}")
                initial_image_order = []
        
        # Находим все целевые области
        target_areas = task_form.find_elements(By.CSS_SELECTOR, ".LinkTaskRow_linkRowTarget__D79Ny")
        drop_areas = task_form.find_elements(By.CSS_SELECTOR, ".LinkTaskRow_linkRowContent__XBn6u")
        
        print(f"  Найдено целевых областей: {len(target_areas)}")
        print(f"  Найдено областей для размещения: {len(drop_areas)}")
        
        # Преобразуем mappings в список кортежей, если это словарь
        if isinstance(mappings, dict):
            mappings = list(mappings.items())
        
        matched_count = 0
        for target_text, element_text in mappings:
            print(f"  Сопоставляем '{element_text}' -> '{target_text}'")
            
            # Обновляем форму и все списки перед каждым поиском
            # (так как элементы могут быть перемещены)
            task_form = get_task_form(driver)
            target_areas = task_form.find_elements(By.CSS_SELECTOR, ".LinkTaskRow_linkRowTarget__D79Ny")
            drop_areas = task_form.find_elements(By.CSS_SELECTOR, ".LinkTaskRow_linkRowContent__XBn6u")
            
            # Находим элемент для перетаскивания
            source_element = None
            
            # Если это изображения, используем сопоставление по индексу
            if has_images:
                try:
                    # Пытаемся преобразовать element_text в индекс (номер изображения)
                    # Может быть числом или строкой с числом
                    if isinstance(element_text, (int, float)):
                        image_index = int(element_text) - 1  # Индексы начинаются с 0
                    else:
                        # Пробуем извлечь число из строки
                        import re
                        numbers = re.findall(r'\d+', str(element_text))
                        if numbers:
                            image_index = int(numbers[0]) - 1  # Берем первое число
                        else:
                            print(f"    ⚠ Не удалось извлечь индекс из '{element_text}', пропускаем")
                            continue
                    
                    target_idx_str = str(target_index) if 'target_index' in locals() and target_index is not None else '?'
                    print(f"    Ищем изображение по индексу: {image_index + 1} (для целевой области #{target_idx_str})")
                    
                    # Используем сохраненный исходный порядок изображений, если он есть
                    if initial_image_order and image_index < len(initial_image_order):
                        # Находим актуальное изображение из текущего DOM по сохраненному индексу
                        try:
                            # Используем JavaScript для поиска актуального элемента по исходному индексу
                            # Важно: находим изображения в исходном порядке, исключая уже перемещенные
                            source_element = driver.execute_script("""
                                var optionsPanel = arguments[0];
                                var originalIndex = arguments[1];
                                var allOptions = optionsPanel.querySelectorAll('.OptionsSlide_image__nlliP, .styled__ImageOption-ftJQiu');
                                
                                // Если не нашли по классам, ищем все draggable элементы
                                if (allOptions.length === 0) {
                                    allOptions = optionsPanel.querySelectorAll('[draggable="true"]');
                                }
                                
                                // ВАЖНО: Для multi-use drag and drop элементы остаются в панели опций
                                // Поэтому мы должны использовать исходный порядок из DOM, а не фильтровать перемещенные
                                // Собираем все изображения в исходном порядке DOM
                                var imageElements = [];
                                for (var i = 0; i < allOptions.length; i++) {
                                    var option = allOptions[i];
                                    
                                    // Для multi-use типа не проверяем, перемещен ли элемент
                                    // (элементы остаются в панели опций)
                                    
                                    // Проверяем наличие изображения
                                    var hasImage = option.querySelector('.styled__ImageContent-eNVTVI, .styled__ImageContent');
                                    if (hasImage || option.getAttribute('draggable') === 'true') {
                                        // Находим draggable элемент внутри или используем сам option
                                        var draggable = option.querySelector('[draggable="true"]');
                                        if (!draggable && option.getAttribute('draggable') === 'true') {
                                            draggable = option;
                                        }
                                        if (draggable) {
                                            imageElements.push(draggable);
                                        }
                                    }
                                }
                                
                                // Возвращаем элемент по исходному индексу из DOM (независимо от того, перемещен он или нет)
                                if (originalIndex < imageElements.length) {
                                    return imageElements[originalIndex];
                                }
                                
                                // Если индекс выходит за пределы, возможно некоторые изображения уже перемещены
                                // Пробуем найти по позиции среди всех доступных изображений
                                return null;
                            """, task_form.find_element(By.CSS_SELECTOR, ".Options_root__q5QuO, .Options_optionsRows__JttWG, .LinkTask_optionsPanel__GLzIR"), image_index, is_multi_use)
                            
                            if source_element:
                                print(f"    ✓ Найдено изображение по исходному индексу {image_index + 1}")
                            else:
                                print(f"    ⚠ Изображение с индексом {image_index + 1} не найдено в текущем DOM, ищем среди доступных...")
                        except Exception as e:
                            print(f"    ⚠ Ошибка при поиске изображения по исходному индексу: {e}")
                            source_element = None
                    
                    # Если не нашли по исходному порядку, используем обычный поиск
                    if not source_element:
                        # Получаем все изображения из панели опций (еще не перемещенные)
                        # Ищем в панели опций Options_root__q5QuO или Options_optionsRows__JttWG
                        available_images = []
                        
                        try:
                            # Ищем панель опций
                            options_panel = task_form.find_element(By.CSS_SELECTOR, ".Options_root__q5QuO, .Options_optionsRows__JttWG, .LinkTask_optionsPanel__GLzIR")
                            
                            # Находим все элементы с изображениями в панели опций
                            # Ищем элементы с классом OptionsSlide_image__nlliP или styled__ImageOption
                            # Сначала ищем все контейнеры опций с изображениями
                            image_containers = options_panel.find_elements(By.CSS_SELECTOR, ".OptionsSlide_image__nlliP, .styled__ImageOption-ftJQiu")
                            
                            # Если не нашли по классам, ищем все элементы с draggable='true'
                            if not image_containers:
                                image_containers = options_panel.find_elements(By.CSS_SELECTOR, "[draggable='true']")
                            
                            for option in image_containers:
                                try:
                                    # Для multi-use типа не проверяем, перемещен ли элемент
                                    # (элементы остаются в панели опций и могут использоваться повторно)
                                    if not is_multi_use:
                                        # Проверяем, что элемент еще не перемещен (не находится в drop area)
                                        try:
                                            parent = option.find_element(By.XPATH, "./ancestor::div[contains(@class, 'LinkTaskRow_linkRowContent__XBn6u')]")
                                            continue  # Элемент уже перемещен
                                        except:
                                            pass
                                    
                                    # Проверяем наличие изображения
                                    has_image = False
                                    try:
                                        image_content = option.find_element(By.CSS_SELECTOR, ".styled__ImageContent-eNVTVI, .styled__ImageContent")
                                        has_image = True
                                    except:
                                        # Проверяем, есть ли изображение в дочерних элементах
                                        try:
                                            image_content = option.find_element(By.CSS_SELECTOR, ".styled__ImageContent")
                                            has_image = True
                                        except:
                                            pass
                                    
                                    # Если есть изображение или это draggable элемент, добавляем
                                    if has_image or option.get_attribute("draggable") == "true":
                                        # Находим draggable элемент внутри или используем сам option
                                        try:
                                            draggable = option.find_element(By.CSS_SELECTOR, "[draggable='true']")
                                            # Проверяем еще раз, что draggable не перемещен
                                            try:
                                                parent = draggable.find_element(By.XPATH, "./ancestor::div[contains(@class, 'LinkTaskRow_linkRowContent__XBn6u')]")
                                                continue  # Элемент уже перемещен
                                            except:
                                                available_images.append(draggable)
                                        except:
                                            # Если нет draggable внутри, но option сам draggable
                                            if option.get_attribute("draggable") == "true":
                                                available_images.append(option)
                                except:
                                    continue
                        except:
                            # Fallback: используем старый метод
                            draggable_elements = task_form.find_elements(By.CSS_SELECTOR, "[draggable='true']")
                            for draggable in draggable_elements:
                                try:
                                    # Проверяем, что элемент еще не перемещен
                                    try:
                                        parent = draggable.find_element(By.XPATH, "./ancestor::div[contains(@class, 'LinkTaskRow_linkRowContent__XBn6u')]")
                                        continue  # Элемент уже перемещен
                                    except:
                                        pass
                                    
                                    # Проверяем наличие изображения
                                    try:
                                        image_content = draggable.find_element(By.CSS_SELECTOR, ".styled__ImageContent-eNVTVI, .styled__ImageContent")
                                        available_images.append(draggable)
                                    except:
                                        # Если нет изображения, но это draggable элемент, тоже добавляем
                                        available_images.append(draggable)
                                except:
                                    continue
                        
                        print(f"    [DEBUG] Доступно изображений: {len(available_images)}")
                        
                        if len(available_images) == 0:
                            print(f"    ⚠ Не найдено доступных изображений, пробуем альтернативный метод...")
                            # Альтернативный метод: ищем все изображения в панели опций без фильтрации по draggable
                            try:
                                options_panel = task_form.find_element(By.CSS_SELECTOR, ".Options_root__q5QuO, .Options_optionsRows__JttWG, .LinkTask_optionsPanel__GLzIR")
                                all_image_elements = options_panel.find_elements(By.CSS_SELECTOR, ".styled__ImageContent-eNVTVI, .styled__ImageContent")
                                print(f"    [DEBUG] Найдено элементов с изображениями в панели: {len(all_image_elements)}")
                                
                                # Находим родительские draggable элементы
                                for img_elem in all_image_elements:
                                    try:
                                        # Находим ближайший draggable родитель
                                        draggable_parent = img_elem.find_element(By.XPATH, "./ancestor::*[@draggable='true'][1]")
                                        # Проверяем, что элемент еще не перемещен
                                        try:
                                            parent = draggable_parent.find_element(By.XPATH, "./ancestor::div[contains(@class, 'LinkTaskRow_linkRowContent__XBn6u')]")
                                            continue  # Элемент уже перемещен
                                        except:
                                            available_images.append(draggable_parent)
                                    except:
                                        continue
                                
                                print(f"    [DEBUG] После альтернативного поиска доступно изображений: {len(available_images)}")
                            except Exception as alt_e:
                                print(f"    ⚠ Ошибка при альтернативном поиске: {alt_e}")
                        
                        if 0 <= image_index < len(available_images):
                            source_element = available_images[image_index]
                            print(f"    ✓ Найдено изображение по индексу {image_index + 1}")
                        else:
                            print(f"    ⚠ Индекс {image_index + 1} выходит за пределы доступных изображений (всего: {len(available_images)})")
                            # Пробуем найти по порядковому номеру среди всех изображений в панели
                            if len(available_images) > 0:
                                print(f"    [DEBUG] Пробуем использовать последнее доступное изображение...")
                                source_element = available_images[-1]
                                print(f"    ⚠ Используем последнее доступное изображение (индекс {len(available_images)})")
                            else:
                                continue
                            
                except Exception as e:
                    print(f"    ⚠ Ошибка при поиске изображения по индексу: {e}")
                    continue
            
            # Если это не изображения или не удалось найти по индексу, используем поиск по тексту
            if not source_element:
                # Находим элемент для перетаскивания по тексту
                # Ищем во всех возможных контейнерах опций, не только с draggable='true'
                
                # Сначала ищем среди элементов с draggable='true' (еще не перемещенные)
                draggable_elements = task_form.find_elements(By.CSS_SELECTOR, "[draggable='true']")
                for draggable in draggable_elements:
                    try:
                        # Проверяем, что элемент еще не перемещен (не находится внутри drop area)
                        try:
                            # Если элемент уже внутри drop area, пропускаем его
                            parent = draggable.find_element(By.XPATH, "./ancestor::div[contains(@class, 'LinkTaskRow_linkRowContent__XBn6u')]")
                            # Элемент уже перемещен, пропускаем
                            continue
                        except:
                            # Элемент еще не перемещен, продолжаем
                            pass
                        
                        # Пробуем извлечь текст из span с классом MathContent_content
                        text = ""
                        try:
                            # Сначала пробуем найти span с классом MathContent_content
                            span = draggable.find_element(By.XPATH, ".//span[contains(@class, 'MathContent_content')]")
                            text = span.text.strip()
                        except:
                            try:
                                # Если не нашли, пробуем найти в родительских элементах
                                parent = draggable.find_element(By.XPATH, "./ancestor::div[contains(@class, 'OptionsSlide_option__PBAys')]")
                                span = parent.find_element(By.XPATH, ".//span[contains(@class, 'MathContent_content')]")
                                text = span.text.strip()
                            except:
                                try:
                                    # Пробуем получить текст напрямую из элемента
                                    text = draggable.text.strip()
                                except:
                                    # Последняя попытка - через JavaScript
                                    try:
                                        text = driver.execute_script("""
                                            var el = arguments[0];
                                            var span = el.querySelector('.MathContent_content__2a8XE');
                                            if (span) return span.textContent.trim();
                                            return el.textContent.trim();
                                        """, draggable)
                                    except:
                                        text = ""
                        
                        # Нормализуем тексты для сравнения
                        if text:
                            text_normalized = ' '.join(text.lower().split())
                            element_normalized = ' '.join(element_text.lower().split())
                            
                            # Проверяем совпадение (частичное или полное)
                            if element_normalized in text_normalized or text_normalized in element_normalized:
                                source_element = draggable
                                print(f"      Найден draggable элемент: '{text}'")
                                break
                    except:
                        continue
            
            # Если не нашли среди draggable элементов, ищем во всех контейнерах опций
            if not source_element:
                # Ищем во всех контейнерах опций (включая те, что уже могут быть перемещены, но еще не в drop areas)
                all_option_containers = task_form.find_elements(By.CSS_SELECTOR, ".OptionsSlide_option__PBAys, .styled__Wrapper-cixSOf")
                for container in all_option_containers:
                    try:
                        # Проверяем, что контейнер еще не находится в drop area
                        # Для multi-use типа элементы остаются в панели опций, поэтому ищем в панели опций
                        if not is_multi_use:
                            try:
                                parent = container.find_element(By.XPATH, "./ancestor::div[contains(@class, 'LinkTaskRow_linkRowContent__XBn6u')]")
                                # Контейнер уже в drop area, пропускаем
                                continue
                            except:
                                # Контейнер еще не перемещен, проверяем текст
                                pass
                        else:
                            # Для multi-use типа: ищем элементы только в панели опций
                            try:
                                options_panel = container.find_element(By.XPATH, "./ancestor::div[contains(@class, 'LinkTask_optionsPanel__GLzIR') or contains(@class, 'Options_root__q5QuO') or contains(@class, 'Options_optionsRows__JttWG')]")
                                # Элемент в панели опций - это хорошо, продолжаем
                            except:
                                # Элемент не в панели опций, возможно уже перемещен, но для multi-use это нормально
                                # Проверяем, находится ли он в drop area - если да, пропускаем (ищем оригинал в панели)
                                try:
                                    parent = container.find_element(By.XPATH, "./ancestor::div[contains(@class, 'LinkTaskRow_linkRowContent__XBn6u')]")
                                    # Элемент в drop area, пропускаем (ищем оригинал в панели опций)
                                    continue
                                except:
                                    # Элемент не в drop area, возможно в панели опций, продолжаем
                                    pass
                        
                        # Проверяем, есть ли внутри draggable элемент
                        try:
                            draggable_in_container = container.find_element(By.CSS_SELECTOR, "[draggable='true']")
                            # Есть draggable элемент, проверяем текст
                            try:
                                span = draggable_in_container.find_element(By.XPATH, ".//span[contains(@class, 'MathContent_content')]")
                                text = span.text.strip()
                            except:
                                text = draggable_in_container.text.strip()
                            
                            text_normalized = ' '.join(text.lower().split())
                            element_normalized = ' '.join(element_text.lower().split())
                            
                            if element_normalized in text_normalized or text_normalized in element_normalized:
                                source_element = draggable_in_container
                                print(f"      Найден draggable элемент в контейнере: '{text}'")
                                break
                        except:
                            # Нет draggable элемента, но проверяем текст контейнера
                            try:
                                span = container.find_element(By.XPATH, ".//span[contains(@class, 'MathContent_content')]")
                                text = span.text.strip()
                            except:
                                text = container.text.strip()
                            
                            text_normalized = ' '.join(text.lower().split())
                            element_normalized = ' '.join(element_text.lower().split())
                            
                            if element_normalized in text_normalized or text_normalized in element_normalized:
                                # Находим draggable элемент внутри или используем контейнер
                                try:
                                    source_element = container.find_element(By.CSS_SELECTOR, "[draggable='true']")
                                except:
                                    source_element = container
                                print(f"      Найден элемент в контейнере: '{text}'")
                                break
                    except:
                        continue
            
            # Находим целевую область по тексту
            target_area = None
            target_index = None  # Сохраняем индекс целевой области для отладки
            for idx, target in enumerate(target_areas):
                try:
                    # Пробуем извлечь текст из span с классом MathContent_content
                    try:
                        span = target.find_element(By.XPATH, ".//span[contains(@class, 'MathContent_content')]")
                        text = span.text.strip()
                    except:
                        text = target.text.strip()
                    
                    # Нормализуем тексты для сравнения
                    text_normalized = ' '.join(text.lower().split())
                    target_normalized = ' '.join(target_text.lower().split())
                    
                    # Проверяем совпадение (частичное или полное)
                    if target_normalized in text_normalized or text_normalized in target_normalized:
                        # Находим соответствующую drop область (следующий sibling)
                        parent = target.find_element(By.XPATH, "./..")
                        drop_area = parent.find_element(By.CSS_SELECTOR, ".LinkTaskRow_linkRowContent__XBn6u")
                        target_area = drop_area
                        target_index = idx + 1  # Индекс начинается с 1 (сверху вниз)
                        print(f"      Найдена целевая область #{target_index} (сверху вниз): '{text[:50]}...'")
                        break
                except:
                    continue
            
            if source_element and target_area:
                try:
                    # Убеждаемся что элементы полностью видны
                    driver.execute_script("""
                        var source = arguments[0];
                        var target = arguments[1];
                        
                        // Прокручиваем исходный элемент в центр экрана
                        source.scrollIntoView({block: 'center', inline: 'center', behavior: 'instant'});
                        
                        // Прокручиваем целевую область в центр экрана
                        target.scrollIntoView({block: 'center', inline: 'center', behavior: 'instant'});
                        
                        // Убеждаемся что элементы видимы
                        var sourceRect = source.getBoundingClientRect();
                        var targetRect = target.getBoundingClientRect();
                        
                        // Если элемент частично скрыт, прокручиваем еще раз
                        if (sourceRect.top < 0 || sourceRect.bottom > window.innerHeight) {
                            source.scrollIntoView({block: 'center', inline: 'center'});
                        }
                        if (targetRect.top < 0 || targetRect.bottom > window.innerHeight) {
                            target.scrollIntoView({block: 'center', inline: 'center'});
                        }
                    """, source_element, target_area)
                    time.sleep(0.3)
                    
                    # Используем JavaScript для перетаскивания (более надежно чем ActionChains)
                    # Передаем element_text для правильного определения значения (особенно важно для изображений)
                    success = driver.execute_script("""
                        var source = arguments[0];
                        var target = arguments[1];
                        var isMultiUse = arguments[2] || false;
                        var elementIndex = arguments[3] || null; // Индекс элемента (для изображений)
                        var elementIndex = arguments[3] || null; // Индекс элемента (для изображений)
                        
                        try {
                            // Проверяем, не находится ли элемент уже в целевой области
                            // Для multi-use типа это не важно, так как элемент остается в панели
                            if (!isMultiUse && (target.contains(source) || target.contains(source.parentElement))) {
                                return true; // Уже перемещен
                            }
                            
                            // Находим правильный контейнер опции (draggable элемент)
                            var draggableElement = source;
                            if (!draggableElement.hasAttribute('draggable')) {
                                draggableElement = source.closest('[draggable="true"]') || source;
                            }
                            
                            // Находим контейнер опции
                            var optionContainer = draggableElement.closest('.OptionsSlide_option__PBAys') || 
                                                  draggableElement.closest('.styled__Wrapper-cixSOf') ||
                                                  draggableElement.parentElement;
                            
                            if (!optionContainer) {
                                return false;
                            }
                            
                            // Для multi-use типа: проверяем, что элемент находится в панели опций
                            if (isMultiUse) {
                                var optionsPanel = optionContainer.closest('.LinkTask_optionsPanel__GLzIR, .Options_root__q5QuO, .Options_optionsRows__JttWG');
                                if (!optionsPanel) {
                                    // Если элемент не в панели опций, значит он уже перемещен
                                    // Для multi-use это нормально - мы можем использовать его снова
                                    // Но нужно найти исходный элемент в панели опций
                                    var form = target.closest('form');
                                    if (form) {
                                        var allOptions = form.querySelectorAll('.LinkTask_optionsPanel__GLzIR [draggable="true"], .Options_root__q5QuO [draggable="true"]');
                                        // Ищем элемент с таким же текстом
                                        var sourceText = source.textContent.trim() || source.querySelector('.MathContent_content__2a8XE')?.textContent.trim() || '';
                                        for (var i = 0; i < allOptions.length; i++) {
                                            var opt = allOptions[i];
                                            var optText = opt.textContent.trim() || opt.querySelector('.MathContent_content__2a8XE')?.textContent.trim() || '';
                                            if (optText === sourceText && optText !== '') {
                                                draggableElement = opt;
                                                optionContainer = draggableElement.closest('.OptionsSlide_option__PBAys') || 
                                                                  draggableElement.closest('.styled__Wrapper-cixSOf') ||
                                                                  draggableElement.parentElement;
                                                break;
                                            }
                                        }
                                    }
                                }
                            }
                            
                            // Получаем ID или данные элемента для передачи
                            var elementId = draggableElement.getAttribute('data-id') || 
                                          draggableElement.id || 
                                          optionContainer.getAttribute('data-id') ||
                                          '';
                            
                            // Создаем правильный DataTransfer объект
                            var dataTransfer = new DataTransfer();
                            if (elementId) {
                                dataTransfer.setData('text/plain', elementId);
                                dataTransfer.setData('application/json', JSON.stringify({id: elementId}));
                            }
                            
                            // 1. Инициируем dragstart на исходном элементе (только если элемент еще не перетаскивается)
                            try {
                                var dragStartEvent = new DragEvent('dragstart', { 
                                    bubbles: true, 
                                    cancelable: true,
                                    dataTransfer: dataTransfer
                                });
                                draggableElement.dispatchEvent(dragStartEvent);
                            } catch (e) {
                                console.log('Ошибка при dragstart (возможно уже перетаскивается):', e);
                            }
                            
                            // 2. Инициируем dragover на целевой области (без hover, чтобы избежать ошибок React DnD)
                            try {
                                var dragOverEvent = new DragEvent('dragover', { 
                                    bubbles: true, 
                                    cancelable: true,
                                    dataTransfer: dataTransfer
                                });
                                dragOverEvent.preventDefault(); // Разрешаем drop
                                target.dispatchEvent(dragOverEvent);
                            } catch (e) {
                                console.log('Ошибка при dragover:', e);
                            }
                            
                            // 3. Очищаем целевую область (удаляем пустые элементы)
                            var emptySpans = target.querySelectorAll('span.MathContent_content__2a8XE');
                            emptySpans.forEach(function(span) {
                                if (span.textContent.trim() === '') {
                                    var parent = span.closest('.styled__TextOption');
                                    if (parent) {
                                        parent.remove();
                                    }
                                }
                            });
                            
                            // 4. Клонируем контейнер опции
                            var clone = optionContainer.cloneNode(true);
                            
                            // Удаляем атрибут draggable у всех элементов внутри клона
                            var draggables = clone.querySelectorAll('[draggable="true"]');
                            draggables.forEach(function(el) {
                                el.removeAttribute('draggable');
                            });
                            
                            // 5. Добавляем клон в целевую область
                            target.appendChild(clone);
                            
                            // 6. Инициируем drop событие на целевой области
                            var dropEvent = new DragEvent('drop', { 
                                bubbles: true, 
                                cancelable: true,
                                dataTransfer: dataTransfer
                            });
                            dropEvent.preventDefault();
                            target.dispatchEvent(dropEvent);
                            
                            // 7. Удаляем исходный элемент только если это НЕ multi-use тип
                            if (!isMultiUse) {
                                optionContainer.remove();
                            }
                            
                            // 8. Инициируем dragend
                            var dragEndEvent = new DragEvent('dragend', { 
                                bubbles: true, 
                                cancelable: true,
                                dataTransfer: dataTransfer
                            });
                            var form = target.closest('form');
                            if (form) {
                                form.dispatchEvent(dragEndEvent);
                            }
                            
                            // 9. Обновляем скрытые поля формы с правильными значениями
                            if (form) {
                                // Ищем input поля внутри текущей drop area
                                var inputInTarget = target.querySelector('input[type="hidden"]');
                                
                                // Определяем значение для установки
                                var valueToSet = null;
                                
                                // Если передан индекс элемента (для изображений), используем его
                                if (elementIndex !== null && elementIndex !== undefined && elementIndex !== '') {
                                    valueToSet = String(elementIndex);
                                    console.log('Используем индекс элемента для установки значения:', valueToSet);
                                } else {
                                    // Для текстовых элементов получаем значение из перетащенного элемента
                                    var optionText = clone.textContent.trim() || 
                                                    clone.querySelector('.MathContent_content')?.textContent.trim() || 
                                                    clone.querySelector('span')?.textContent.trim() || '';
                                    
                                    // Пробуем найти data-id или другой идентификатор
                                    var optionId = clone.getAttribute('data-id') || 
                                                  clone.querySelector('[data-id]')?.getAttribute('data-id') ||
                                                  draggableElement.getAttribute('data-id') ||
                                                  optionContainer.getAttribute('data-id') || '';
                                    
                                    valueToSet = optionId || optionText;
                                }
                                
                                if (inputInTarget) {
                                    console.log('Найден input в drop area:', inputInTarget.name || inputInTarget.id, 'текущее значение:', inputInTarget.value, 'новое значение:', valueToSet);
                                    
                                    // Устанавливаем значение
                                    inputInTarget.value = valueToSet;
                                    
                                    // Инициируем события для обновления React состояния
                                    var inputEvent = new Event('input', { bubbles: true, cancelable: true });
                                    inputInTarget.dispatchEvent(inputEvent);
                                    
                                    var changeEvent = new Event('change', { bubbles: true, cancelable: true });
                                    inputInTarget.dispatchEvent(changeEvent);
                                    
                                    // Также пробуем установить значение через свойство напрямую
                                    Object.defineProperty(inputInTarget, 'value', {
                                        value: valueToSet,
                                        writable: true
                                    });
                                    inputInTarget.dispatchEvent(new Event('input', { bubbles: true }));
                                    inputInTarget.dispatchEvent(new Event('change', { bubbles: true }));
                                    
                                    console.log('Значение после обновления:', inputInTarget.value);
                                } else {
                                    console.log('⚠ Input не найден в drop area, ищем в корне формы...');
                                    // Ищем input в корне формы по индексу drop area
                                    var allHiddenInputs = form.querySelectorAll('input[type="hidden"][name*="questions"]');
                                    var dropAreas = form.querySelectorAll('.LinkTaskRow_linkRowContent__XBn6u');
                                    var currentIndex = -1;
                                    for (var i = 0; i < dropAreas.length; i++) {
                                        if (dropAreas[i] === target) {
                                            currentIndex = i;
                                            break;
                                        }
                                    }
                                    
                                    if (currentIndex >= 0) {
                                        if (currentIndex < allHiddenInputs.length) {
                                            var inputInForm = allHiddenInputs[currentIndex];
                                            console.log('Найден input в корне формы по индексу:', inputInForm.name, 'текущее значение:', inputInForm.value, 'новое значение:', valueToSet);
                                            inputInForm.value = valueToSet;
                                            Object.defineProperty(inputInForm, 'value', {
                                                value: valueToSet,
                                                writable: true,
                                                configurable: true
                                            });
                                            inputInForm.dispatchEvent(new Event('input', { bubbles: true, cancelable: true }));
                                            inputInForm.dispatchEvent(new Event('change', { bubbles: true, cancelable: true }));
                                            console.log('Значение после обновления:', inputInForm.value);
                                        } else {
                                            // Создаем новый input для последнего элемента
                                            console.log('Создаем новый input для индекса', currentIndex);
                                            var firstInput = allHiddenInputs[0];
                                            if (firstInput && valueToSet) {
                                                var namePattern = firstInput.name;
                                                var match = namePattern.match(/questions\[(\d+)\]/);
                                                if (match) {
                                                    var questionId = match[1];
                                                    var lastInput = allHiddenInputs[allHiddenInputs.length - 1];
                                                    var lastMatch = lastInput.name.match(/\[(\d+)\]$/);
                                                    var nextId = lastMatch ? String(parseInt(lastMatch[1]) + 1) : '10009546';
                                                    
                                                    var newInput = document.createElement('input');
                                                    newInput.type = 'hidden';
                                                    newInput.name = 'questions[' + questionId + '][' + nextId + ']';
                                                    newInput.tabIndex = -1;
                                                    newInput.value = valueToSet;
                                                    
                                                    // Вставляем в корень формы
                                                    var linkRoot = form.querySelector('[class*="Link_root"]') || form.querySelector('div > div > div');
                                                    if (linkRoot) {
                                                        linkRoot.appendChild(newInput);
                                                    } else {
                                                        form.appendChild(newInput);
                                                    }
                                                    
                                                    newInput.dispatchEvent(new Event('input', { bubbles: true, cancelable: true }));
                                                    newInput.dispatchEvent(new Event('change', { bubbles: true, cancelable: true }));
                                                    console.log('✓ Создан новый input:', newInput.name, '=', valueToSet);
                                                }
                                            }
                                        }
                                    } else if (currentIndex >= 0 && currentIndex >= allHiddenInputs.length) {
                                        // Создаем новый input для последнего элемента
                                        console.log('Создаем новый input для индекса', currentIndex, 'значение:', valueToSet);
                                        var firstInput = allHiddenInputs[0];
                                        if (firstInput && valueToSet) {
                                            var namePattern = firstInput.name;
                                            var match = namePattern.match(/questions\[(\d+)\]/);
                                            if (match) {
                                                var questionId = match[1];
                                                var lastInput = allHiddenInputs[allHiddenInputs.length - 1];
                                                var lastMatch = lastInput.name.match(/\[(\d+)\]$/);
                                                var nextId = lastMatch ? String(parseInt(lastMatch[1]) + 1) : '10009546';
                                                
                                                var newInput = document.createElement('input');
                                                newInput.type = 'hidden';
                                                newInput.name = 'questions[' + questionId + '][' + nextId + ']';
                                                newInput.tabIndex = -1;
                                                newInput.value = valueToSet;
                                                
                                                // Вставляем в корень формы
                                                var linkRoot = form.querySelector('[class*="Link_root"]') || form.querySelector('div > div > div');
                                                if (linkRoot) {
                                                    linkRoot.appendChild(newInput);
                                                } else {
                                                    form.appendChild(newInput);
                                                }
                                                
                                                Object.defineProperty(newInput, 'value', {
                                                    value: valueToSet,
                                                    writable: true,
                                                    configurable: true
                                                });
                                                newInput.dispatchEvent(new Event('input', { bubbles: true, cancelable: true }));
                                                newInput.dispatchEvent(new Event('change', { bubbles: true, cancelable: true }));
                                                console.log('✓ Создан новый input:', newInput.name, '=', valueToSet);
                                            }
                                        }
                                    } else {
                                        // Ищем input в родительских элементах
                                        var parent = target.closest('.LinkTaskRow_linkRow__36TU1');
                                        if (parent) {
                                            var inputInParent = parent.querySelector('input[type="hidden"]');
                                            if (inputInParent) {
                                                console.log('Найден input в родительском элементе:', inputInParent.name || inputInParent.id);
                                                inputInParent.value = valueToSet;
                                                inputInParent.dispatchEvent(new Event('input', { bubbles: true }));
                                                inputInParent.dispatchEvent(new Event('change', { bubbles: true }));
                                            }
                                        }
                                    }
                                }
                                
                                // Также обновляем все скрытые поля формы на основе содержимого drop areas
                                var hiddenInputs = form.querySelectorAll('input[type="hidden"]');
                                var dropAreas = form.querySelectorAll('.LinkTaskRow_linkRowContent__XBn6u');
                                
                                dropAreas.forEach(function(dropArea, index) {
                                    var option = dropArea.querySelector('.OptionsSlide_option__PBAys, .styled__Wrapper-cixSOf');
                                    if (option) {
                                        var optionText = option.textContent.trim() || 
                                                        option.querySelector('.MathContent_content')?.textContent.trim() || 
                                                        option.querySelector('span')?.textContent.trim() || '';
                                        
                                        var optionId = option.getAttribute('data-id') || 
                                                      option.querySelector('[data-id]')?.getAttribute('data-id') || 
                                                      '';
                                        
                                        var valueToSet = optionId || optionText;
                                        
                                        // Ищем input внутри этой drop area
                                        var inputInArea = dropArea.querySelector('input[type="hidden"]');
                                        if (inputInArea && valueToSet) {
                                            inputInArea.value = valueToSet;
                                            inputInArea.dispatchEvent(new Event('input', { bubbles: true }));
                                            inputInArea.dispatchEvent(new Event('change', { bubbles: true }));
                                        }
                                        
                                        // Также ищем скрытые поля по имени/ID
                                        hiddenInputs.forEach(function(input) {
                                            var inputName = (input.name || input.id || '').toLowerCase();
                                            var inputIndex = input.getAttribute('data-index') || 
                                                           input.getAttribute('data-answer-index') ||
                                                           '';
                                            
                                            // Проверяем, соответствует ли поле этой drop area
                                            if ((inputName.includes('answer') && (inputName.includes(String(index)) || inputIndex == index)) ||
                                                (inputName.includes('option') && (inputName.includes(String(index)) || inputIndex == index)) ||
                                                (input.getAttribute('data-row-index') == index) ||
                                                (input.closest('.LinkTaskRow_linkRow__36TU1') === dropArea.closest('.LinkTaskRow_linkRow__36TU1'))) {
                                                
                                                if (valueToSet) {
                                                    input.value = valueToSet;
                                                    input.dispatchEvent(new Event('input', { bubbles: true }));
                                                    input.dispatchEvent(new Event('change', { bubbles: true }));
                                                }
                                            }
                                        });
                                    } else {
                                        // Если в drop area нет опции, очищаем соответствующее поле
                                        var inputInArea = dropArea.querySelector('input[type="hidden"]');
                                        if (inputInArea && !inputInArea.value) {
                                            // Оставляем пустым, если поле уже пустое
                                        }
                                    }
                                });
                            }
                            
                            // 10. Инициируем дополнительные события для обновления формы
                            var changeEvent = new Event('change', { bubbles: true, cancelable: true });
                            target.dispatchEvent(changeEvent);
                            
                            var inputEvent = new Event('input', { bubbles: true, cancelable: true });
                            target.dispatchEvent(inputEvent);
                            
                            // 11. Инициируем события на форме для обновления React состояния
                            if (form) {
                                var formChangeEvent = new Event('change', { bubbles: true, cancelable: true });
                                form.dispatchEvent(formChangeEvent);
                                
                                var formInputEvent = new Event('input', { bubbles: true, cancelable: true });
                                form.dispatchEvent(formInputEvent);
                                
                                // Пробуем обновить React состояние через синтетические события
                                try {
                                    var reactEvent = new Event('change', { bubbles: true, cancelable: true });
                                    Object.defineProperty(reactEvent, 'target', {
                                        value: target,
                                        writable: false
                                    });
                                    form.dispatchEvent(reactEvent);
                                } catch(e) {}
                                
                                // Принудительно обновляем все скрытые поля еще раз
                                hiddenInputs = form.querySelectorAll('input[type="hidden"]');
                                hiddenInputs.forEach(function(input) {
                                    var inputEvent = new Event('change', { bubbles: true });
                                    input.dispatchEvent(inputEvent);
                                });
                            }
                            
                            return true;
                        } catch (e) {
                            console.error('Ошибка при перемещении:', e);
                            return false;
                        }
                    """, source_element, target_area, is_multi_use, str(element_text) if has_images else None)
                    
                    time.sleep(1)  # Увеличиваем время ожидания для обновления UI и состояния формы
                    
                    if success:
                        print(f"    ✓ Перетащено через JavaScript: '{element_text}' в '{target_text}'")
                        matched_count += 1
                        
                        # Дополнительная проверка и обновление скрытых полей
                        try:
                            # Ждем немного для обновления DOM
                            time.sleep(0.5)
                            
                            # Принудительно обновляем скрытые поля в целевой области
                            driver.execute_script("""
                                var target = arguments[0];
                                var form = target.closest('form');
                                
                                if (form) {
                                    // Находим input в текущей drop area
                                    var inputInTarget = target.querySelector('input[type="hidden"]');
                                    if (inputInTarget) {
                                        // Получаем текст из перетащенного элемента
                                        var option = target.querySelector('.OptionsSlide_option__PBAys, .styled__Wrapper-cixSOf');
                                        if (option) {
                                            var optionText = option.textContent.trim() || 
                                                            option.querySelector('.MathContent_content')?.textContent.trim() || 
                                                            option.querySelector('span')?.textContent.trim() || '';
                                            
                                            var optionId = option.getAttribute('data-id') || 
                                                          option.querySelector('[data-id]')?.getAttribute('data-id') || '';
                                            
                                            var valueToSet = optionId || optionText;
                                            
                                            console.log('Дополнительная проверка - input:', inputInTarget.name || inputInTarget.id, 'текущее:', inputInTarget.value, 'новое:', valueToSet);
                                            
                                            if (valueToSet && inputInTarget.value !== valueToSet) {
                                                inputInTarget.value = valueToSet;
                                                inputInTarget.dispatchEvent(new Event('input', { bubbles: true, cancelable: true }));
                                                inputInTarget.dispatchEvent(new Event('change', { bubbles: true, cancelable: true }));
                                                console.log('Значение обновлено:', inputInTarget.value);
                                            } else if (!valueToSet) {
                                                console.log('⚠ Значение для установки пустое!');
                                            } else {
                                                console.log('Значение уже установлено правильно');
                                            }
                                        } else {
                                            console.log('⚠ Опция не найдена в drop area');
                                        }
                                    } else {
                                        console.log('⚠ Input не найден в drop area, ищем в родительских элементах...');
                                        // Ищем в родительских элементах
                                        var parent = target.closest('.LinkTaskRow_linkRow__36TU1');
                                        if (parent) {
                                            var inputInParent = parent.querySelector('input[type="hidden"]');
                                            if (inputInParent) {
                                                console.log('Найден input в родительском элементе:', inputInParent.name || inputInParent.id);
                                                var option = target.querySelector('.OptionsSlide_option__PBAys, .styled__Wrapper-cixSOf');
                                                if (option) {
                                                    var optionText = option.textContent.trim() || 
                                                                    option.querySelector('.MathContent_content')?.textContent.trim() || 
                                                                    option.querySelector('span')?.textContent.trim() || '';
                                                    var optionId = option.getAttribute('data-id') || 
                                                                  option.querySelector('[data-id]')?.getAttribute('data-id') || '';
                                                    var valueToSet = optionId || optionText;
                                                    if (valueToSet) {
                                                        inputInParent.value = valueToSet;
                                                        inputInParent.dispatchEvent(new Event('input', { bubbles: true }));
                                                        inputInParent.dispatchEvent(new Event('change', { bubbles: true }));
                                                    }
                                                }
                                            }
                                        }
                                    }
                                    
                                    // Обновляем все drop areas
                                    var dropAreas = form.querySelectorAll('.LinkTaskRow_linkRowContent__XBn6u');
                                    dropAreas.forEach(function(dropArea, index) {
                                        var option = dropArea.querySelector('.OptionsSlide_option__PBAys, .styled__Wrapper-cixSOf');
                                        var inputInArea = dropArea.querySelector('input[type="hidden"]');
                                        
                                        if (option && inputInArea) {
                                            var optionText = option.textContent.trim() || 
                                                            option.querySelector('.MathContent_content__2a8XE')?.textContent.trim() || 
                                                            option.querySelector('.MathContent_content')?.textContent.trim() || 
                                                            option.querySelector('span')?.textContent.trim() || '';
                                            var optionId = option.getAttribute('data-id') || 
                                                          option.querySelector('[data-id]')?.getAttribute('data-id') || '';
                                            var valueToSet = optionId || optionText;
                                            
                                            if (valueToSet) {
                                                // Принудительно устанавливаем значение
                                                inputInArea.value = valueToSet;
                                                Object.defineProperty(inputInArea, 'value', {
                                                    value: valueToSet,
                                                    writable: true,
                                                    configurable: true
                                                });
                                                
                                                inputInArea.dispatchEvent(new Event('input', { bubbles: true, cancelable: true }));
                                                inputInArea.dispatchEvent(new Event('change', { bubbles: true, cancelable: true }));
                                                inputInArea.dispatchEvent(new Event('blur', { bubbles: true, cancelable: true }));
                                                
                                                console.log('Обновлено поле', index, ':', inputInArea.name || inputInArea.id, '=', valueToSet);
                                            }
                                        }
                                    });
                                    
                                    // Инициируем события на форме
                                    var formChangeEvent = new Event('change', { bubbles: true, cancelable: true });
                                    form.dispatchEvent(formChangeEvent);
                                    
                                    var formInputEvent = new Event('input', { bubbles: true, cancelable: true });
                                    form.dispatchEvent(formInputEvent);
                                }
                            """, target_area)
                        except Exception as e:
                            print(f"    ⚠ Ошибка при дополнительном обновлении полей: {e}")
                        
                        matched_count += 1
                        print(f"    ✓ Перетащено '{element_text}' в '{target_text}'")
                    else:
                        # Пробуем еще раз с более простым подходом
                        print(f"    ⚠ Первая попытка не удалась, пробуем упрощенный метод...")
                        try:
                            driver.execute_script("""
                                var source = arguments[0];
                                var target = arguments[1];
                                
                                var optionContainer = source.closest('.OptionsSlide_option__PBAys') || source.parentElement;
                                if (!optionContainer) return false;
                                
                                var clone = optionContainer.cloneNode(true);
                                clone.querySelectorAll('[draggable="true"]').forEach(function(el) {
                                    el.removeAttribute('draggable');
                                });
                                
                                target.innerHTML = ''; // Очищаем целевую область
                                target.appendChild(clone);
                                optionContainer.remove();
                                
                                return true;
                            """, source_element, target_area)
                            time.sleep(0.3)
                            # matched_count уже увеличен выше, не увеличиваем снова
                            print(f"    ✓ Перетащено '{element_text}' в '{target_text}' (упрощенный метод)")
                        except:
                            print(f"    ⚠ Не удалось переместить '{element_text}' в '{target_text}'")
                        
                except Exception as e:
                    print(f"    ⚠ Ошибка при перетаскивании: {e}")
                    import traceback
                    traceback.print_exc()
            else:
                print(f"    ⚠ Не найдены элементы для '{element_text}' -> '{target_text}'")
        
        # ФИНАЛЬНОЕ ОБНОВЛЕНИЕ: Принудительно обновляем все скрытые поля после всех перетаскиваний
        if matched_count > 0:
            time.sleep(0.5)  # Даем время DOM полностью обновиться
            
            # ВАЖНО: После всех перетаскиваний обновляем все скрытые поля формы
            # Это особенно важно для последнего элемента
            try:
                task_form = get_task_form(driver)
                print("  Обновляем все скрытые поля формы после перетаскиваний...")
                driver.execute_script("""
                    var form = arguments[0];
                    if (!form) return;
                    
                    // Находим все drop areas
                    var dropAreas = form.querySelectorAll('.LinkTaskRow_linkRowContent__XBn6u');
                    var hiddenInputs = form.querySelectorAll('input[type="hidden"]');
                    
                    console.log('Найдено drop areas:', dropAreas.length);
                    console.log('Найдено hidden inputs:', hiddenInputs.length);
                    
                    // Обновляем каждую drop area
                    dropAreas.forEach(function(dropArea, index) {
                        var option = dropArea.querySelector('.OptionsSlide_option__PBAys, .styled__Wrapper-cixSOf, .styled__ImageOption-ftJQiu');
                        if (option) {
                            // Для изображений ищем data-id или индекс
                            var optionId = option.getAttribute('data-id') || 
                                          option.querySelector('[data-id]')?.getAttribute('data-id') || '';
                            
                            // Для изображений также пробуем найти индекс по позиции в исходной панели
                            var imageContent = option.querySelector('.styled__ImageContent-eNVTVI, .styled__ImageContent');
                            var valueToSet = optionId;
                            
                            // Если это изображение и нет data-id, пробуем найти индекс
                            if (imageContent && !valueToSet) {
                                // Ищем в панели опций исходный элемент с таким же изображением
                                var optionsPanel = form.querySelector('.Options_root__q5QuO, .Options_optionsRows__JttWG, .LinkTask_optionsPanel__GLzIR');
                                if (optionsPanel) {
                                    var allOptions = optionsPanel.querySelectorAll('.OptionsSlide_image__nlliP, .styled__ImageOption-ftJQiu, [draggable="true"]');
                                    for (var i = 0; i < allOptions.length; i++) {
                                        var opt = allOptions[i];
                                        var optImage = opt.querySelector('.styled__ImageContent-eNVTVI, .styled__ImageContent, img');
                                        var optImageSrc = optImage ? (optImage.src || optImage.getAttribute('src')) : null;
                                        var imageSrc = imageContent.src || imageContent.getAttribute('src');
                                        if (optImage && optImageSrc && imageSrc && optImageSrc === imageSrc) {
                                            valueToSet = String(i + 1); // Индекс начинается с 1
                                            break;
                                        }
                                    }
                                }
                            }
                            
                            // Если все еще нет значения, используем текст
                            if (!valueToSet) {
                                var optionText = option.textContent.trim() || 
                                                option.querySelector('.MathContent_content__2a8XE')?.textContent.trim() || 
                                                option.querySelector('.MathContent_content')?.textContent.trim() || '';
                                valueToSet = optionText;
                            }
                            
                            // Ищем input в этой drop area
                            var inputInArea = dropArea.querySelector('input[type="hidden"]');
                            if (inputInArea && valueToSet) {
                                inputInArea.value = valueToSet;
                                Object.defineProperty(inputInArea, 'value', {
                                    value: valueToSet,
                                    writable: true,
                                    configurable: true
                                });
                                inputInArea.dispatchEvent(new Event('input', { bubbles: true, cancelable: true }));
                                inputInArea.dispatchEvent(new Event('change', { bubbles: true, cancelable: true }));
                                console.log('Обновлено поле', index, ':', inputInArea.name || inputInArea.id, '=', valueToSet);
                            }
                            
                            // Также ищем скрытые поля по имени/ID, связанные с этой drop area
                            var parentRow = dropArea.closest('.LinkTaskRow_linkRow__36TU1');
                            if (parentRow) {
                                hiddenInputs.forEach(function(input) {
                                    var inputName = (input.name || input.id || '').toLowerCase();
                                    var inputIndex = input.getAttribute('data-index') || 
                                                   input.getAttribute('data-answer-index') || '';
                                    
                                    // Проверяем, соответствует ли поле этой drop area
                                    if ((inputName.includes('answer') && (inputName.includes(String(index)) || inputIndex == index)) ||
                                        (inputName.includes('option') && (inputName.includes(String(index)) || inputIndex == index)) ||
                                        (input.getAttribute('data-row-index') == index) ||
                                        (input.closest('.LinkTaskRow_linkRow__36TU1') === parentRow)) {
                                        
                                        if (valueToSet) {
                                            input.value = valueToSet;
                                            Object.defineProperty(input, 'value', {
                                                value: valueToSet,
                                                writable: true,
                                                configurable: true
                                            });
                                            input.dispatchEvent(new Event('input', { bubbles: true, cancelable: true }));
                                            input.dispatchEvent(new Event('change', { bubbles: true, cancelable: true }));
                                        }
                                    }
                                });
                            }
                        }
                    });
                    
                    // Инициируем события на форме для обновления React состояния
                    var formChangeEvent = new Event('change', { bubbles: true, cancelable: true });
                    form.dispatchEvent(formChangeEvent);
                    var formInputEvent = new Event('input', { bubbles: true, cancelable: true });
                    form.dispatchEvent(formInputEvent);
                """, task_form)
                print("  ✓ Все скрытые поля формы обновлены")
            except Exception as e:
                print(f"  ⚠ Ошибка при обновлении скрытых полей: {e}")
            
            try:
                task_form = get_task_form(driver)
                driver.execute_script("""
                    var form = arguments[0];
                    if (form) {
                        console.log('=== ФИНАЛЬНОЕ ОБНОВЛЕНИЕ ВСЕХ ПОЛЕЙ ===');
                        
                        // Обновляем все drop areas
                        var dropAreas = form.querySelectorAll('.LinkTaskRow_linkRowContent__XBn6u');
                        console.log('Найдено drop areas:', dropAreas.length);
                        dropAreas.forEach(function(dropArea, index) {
                            // Ищем изображение в drop area - может быть в разных местах
                            var option = dropArea.querySelector('.OptionsSlide_option__PBAys, .styled__Wrapper-cixSOf, .styled__ImageOption-ftJQiu, .OptionsSlide_image__nlliP, .styled__ImageAnswer-hpPSnN');
                            
                            // ВАЖНО: Скрытые поля находятся в корне формы, а не в drop area
                            // Ищем input в корне формы по индексу
                            var allInputs = form.querySelectorAll('input[type="hidden"][name*="questions"]');
                            var inputInArea = null;
                            if (allInputs.length > index) {
                                inputInArea = allInputs[index];
                            }
                            
                            // Если не нашли по индексу, пробуем найти в drop area или родительском элементе
                            if (!inputInArea) {
                                inputInArea = dropArea.querySelector('input[type="hidden"]');
                                if (!inputInArea) {
                                    var parentRow = dropArea.closest('.LinkTaskRow_linkRow__36TU1');
                                    if (parentRow) {
                                        inputInArea = parentRow.querySelector('input[type="hidden"]');
                                    }
                                }
                            }
                            
                            // Если не нашли option, ищем изображение напрямую
                            if (!option) {
                                var imageAnswer = dropArea.querySelector('.styled__ImageAnswer-hpPSnN');
                                if (imageAnswer) {
                                    option = imageAnswer;
                                }
                            }
                            
                            // Если не нашли option, ищем draggable изображение в drop area
                            if (!option) {
                                var draggableImage = dropArea.querySelector('.OptionsSlide_image__nlliP[draggable="true"], .styled__ImageOption-ftJQiu[draggable="true"]');
                                if (draggableImage) {
                                    option = draggableImage;
                                }
                            }
                            
                            if (option && inputInArea) {
                                // Проверяем, является ли это изображением
                                // Ищем изображение в разных местах структуры
                                var imageContent = option.querySelector('.styled__ImageContent-eNVTVI, .styled__ImageContent-hjRbwv, .styled__ImageContent, img');
                                
                                // Если не нашли в option, ищем в drop area напрямую
                                if (!imageContent) {
                                    imageContent = dropArea.querySelector('.styled__ImageContent-eNVTVI, .styled__ImageContent-hjRbwv, .styled__ImageContent, img');
                                }
                                var valueToSet = null;
                                
                                if (imageContent) {
                                    // Для изображений ищем data-id или индекс
                                    var optionId = option.getAttribute('data-id') || 
                                                  option.querySelector('[data-id]')?.getAttribute('data-id') || '';
                                    
                                    if (optionId) {
                                        valueToSet = optionId;
                                    } else {
                                        // Если нет data-id, пробуем найти индекс по изображению в панели опций
                                        var optionsPanel = form.querySelector('.Options_root__q5QuO, .Options_optionsRows__JttWG, .LinkTask_optionsPanel__GLzIR');
                                        if (optionsPanel) {
                                            var allOptions = optionsPanel.querySelectorAll('.OptionsSlide_image__nlliP, .styled__ImageOption-ftJQiu, [draggable="true"]');
                                            for (var i = 0; i < allOptions.length; i++) {
                                                var opt = allOptions[i];
                                                var optImage = opt.querySelector('.styled__ImageContent-eNVTVI, .styled__ImageContent, img');
                                                var optImageSrc = optImage.src || optImage.getAttribute('src');
                                                var imageSrc = imageContent.src || imageContent.getAttribute('src');
                                                if (optImage && optImageSrc && imageSrc && optImageSrc === imageSrc) {
                                                    valueToSet = String(i + 1); // Индекс начинается с 1
                                                    break;
                                                }
                                            }
                                        }
                                        
                                        // Если все еще не найдено, используем индекс по позиции в drop area
                                        if (!valueToSet) {
                                            // Пробуем найти индекс по порядку в исходной панели
                                            var imageSrc = imageContent.src || imageContent.getAttribute('src');
                                            if (imageSrc) {
                                                var allImages = form.querySelectorAll('.styled__ImageContent-eNVTVI, .styled__ImageContent');
                                                for (var j = 0; j < allImages.length; j++) {
                                                    if (allImages[j].src === imageSrc || allImages[j].getAttribute('src') === imageSrc) {
                                                        valueToSet = String(j + 1);
                                                        break;
                                                    }
                                                }
                                            }
                                        }
                                    }
                                } else {
                                    // Для текстовых элементов
                                    var optionText = option.textContent.trim() || 
                                                    option.querySelector('.MathContent_content__2a8XE')?.textContent.trim() || 
                                                    option.querySelector('.MathContent_content')?.textContent.trim() || 
                                                    option.querySelector('span')?.textContent.trim() || '';
                                    var optionId = option.getAttribute('data-id') || 
                                                  option.querySelector('[data-id]')?.getAttribute('data-id') || '';
                                    valueToSet = optionId || optionText;
                                }
                                
                                if (valueToSet) {
                                    // Принудительно устанавливаем значение
                                    inputInArea.value = valueToSet;
                                    
                                    // Устанавливаем через свойство напрямую
                                    Object.defineProperty(inputInArea, 'value', {
                                        value: valueToSet,
                                        writable: true,
                                        configurable: true
                                    });
                                    
                                    // Инициируем все возможные события
                                    inputInArea.dispatchEvent(new Event('input', { bubbles: true, cancelable: true }));
                                    inputInArea.dispatchEvent(new Event('change', { bubbles: true, cancelable: true }));
                                    inputInArea.dispatchEvent(new Event('blur', { bubbles: true, cancelable: true }));
                                    
                                    console.log('ФИНАЛЬНО обновлено поле', index, ':', inputInArea.name || inputInArea.id, '=', valueToSet, 'текущее значение:', inputInArea.value);
                                } else {
                                    console.log('⚠ Поле', index, 'пустое, значение не установлено');
                                    // Если значение не установлено, но есть изображение, пробуем найти индекс по изображению
                                    if (imageContent) {
                                        var imageSrc = imageContent.src || imageContent.getAttribute('src') || imageContent.style.backgroundImage;
                                        console.log('⚠ Пробуем найти индекс по изображению для поля', index);
                                        // Ищем в панели опций
                                        var optionsPanel = form.querySelector('.Options_root__q5QuO, .Options_optionsRows__JttWG, .LinkTask_optionsPanel__GLzIR');
                                        if (optionsPanel) {
                                            var allOptions = optionsPanel.querySelectorAll('.OptionsSlide_image__nlliP, .styled__ImageOption-ftJQiu, [draggable="true"]');
                                            for (var k = 0; k < allOptions.length; k++) {
                                                var opt = allOptions[k];
                                                var optImage = opt.querySelector('.styled__ImageContent-eNVTVI, .styled__ImageContent, img');
                                                if (optImage) {
                                                    var optImageSrc = optImage.src || optImage.getAttribute('src') || optImage.style.backgroundImage;
                                                    if (optImageSrc && imageSrc && optImageSrc === imageSrc) {
                                                        valueToSet = String(k + 1);
                                                        inputInArea.value = valueToSet;
                                                        Object.defineProperty(inputInArea, 'value', {
                                                            value: valueToSet,
                                                            writable: true,
                                                            configurable: true
                                                        });
                                                        inputInArea.dispatchEvent(new Event('input', { bubbles: true, cancelable: true }));
                                                        inputInArea.dispatchEvent(new Event('change', { bubbles: true, cancelable: true }));
                                                        console.log('✓ Найдено и установлено значение для поля', index, ':', valueToSet);
                                                        break;
                                                    }
                                                }
                                            }
                                        }
                                    }
                                }
                            } else {
                                console.log('⚠ Поле', index, 'не найдено (option:', !!option, 'input:', !!inputInArea, ')');
                                // Если input не найден в drop area, ищем в родительских элементах
                                if (!inputInArea) {
                                    var parentRow = dropArea.closest('.LinkTaskRow_linkRow__36TU1');
                                    if (parentRow) {
                                        inputInArea = parentRow.querySelector('input[type="hidden"]');
                                        if (inputInArea) {
                                            console.log('✓ Найден input в родительском элементе для поля', index);
                                            // Пробуем найти значение для изображения
                                            var imageContent = dropArea.querySelector('.styled__ImageContent-eNVTVI, .styled__ImageContent-hjRbwv, .styled__ImageContent, img');
                                            if (imageContent) {
                                                var optionsPanel = form.querySelector('.Options_root__q5QuO, .Options_optionsRows__JttWG, .LinkTask_optionsPanel__GLzIR');
                                                if (optionsPanel) {
                                                    var allOptions = optionsPanel.querySelectorAll('.OptionsSlide_image__nlliP, .styled__ImageOption-ftJQiu, [draggable="true"]');
                                                    for (var k = 0; k < allOptions.length; k++) {
                                                        var opt = allOptions[k];
                                                        var optImage = opt.querySelector('.styled__ImageContent-eNVTVI, .styled__ImageContent, img');
                                                        if (optImage) {
                                                            var optImageSrc = optImage.src || optImage.getAttribute('src') || optImage.style.backgroundImage;
                                                            var imageSrc = imageContent.src || imageContent.getAttribute('src') || imageContent.style.backgroundImage;
                                                            if (optImageSrc && imageSrc && optImageSrc === imageSrc) {
                                                                var valueToSet = String(k + 1);
                                                                inputInArea.value = valueToSet;
                                                                Object.defineProperty(inputInArea, 'value', {
                                                                    value: valueToSet,
                                                                    writable: true,
                                                                    configurable: true
                                                                });
                                                                inputInArea.dispatchEvent(new Event('input', { bubbles: true, cancelable: true }));
                                                                inputInArea.dispatchEvent(new Event('change', { bubbles: true, cancelable: true }));
                                                                console.log('✓ Найдено и установлено значение в родительском элементе для поля', index, ':', valueToSet);
                                                                break;
                                                            }
                                                        }
                                                    }
                                                }
                                            }
                                        }
                                    }
                                }
                                
                                // Если все еще не нашли input, ищем все скрытые поля и пробуем найти нужное по индексу
                                if (!inputInArea) {
                                    var allHiddenInputs = form.querySelectorAll('input[type="hidden"]');
                                    console.log('⚠ Ищем input среди всех скрытых полей (всего:', allHiddenInputs.length, ')');
                                    // Пробуем найти input по индексу или имени
                                    for (var m = 0; m < allHiddenInputs.length; m++) {
                                        var hiddenInput = allHiddenInputs[m];
                                        var inputName = (hiddenInput.name || hiddenInput.id || '').toLowerCase();
                                        var inputIndex = hiddenInput.getAttribute('data-index') || 
                                                       hiddenInput.getAttribute('data-answer-index') || '';
                                        
                                        // Проверяем, соответствует ли поле этой drop area
                                        if ((inputName.includes('answer') && (inputName.includes(String(index)) || inputIndex == index)) ||
                                            (inputName.includes('option') && (inputName.includes(String(index)) || inputIndex == index)) ||
                                            (hiddenInput.getAttribute('data-row-index') == index) ||
                                            (hiddenInput.closest('.LinkTaskRow_linkRow__36TU1') === dropArea.closest('.LinkTaskRow_linkRow__36TU1'))) {
                                            inputInArea = hiddenInput;
                                            console.log('✓ Найден input по индексу/имени для поля', index, ':', inputName || inputIndex);
                                            
                                            // Пробуем найти значение для изображения
                                            var imageContent = dropArea.querySelector('.styled__ImageContent-eNVTVI, .styled__ImageContent-hjRbwv, .styled__ImageContent, img');
                                            if (imageContent && inputInArea) {
                                                var optionsPanel = form.querySelector('.Options_root__q5QuO, .Options_optionsRows__JttWG, .LinkTask_optionsPanel__GLzIR');
                                                if (optionsPanel) {
                                                    var allOptions = optionsPanel.querySelectorAll('.OptionsSlide_image__nlliP, .styled__ImageOption-ftJQiu, [draggable="true"]');
                                                    for (var k = 0; k < allOptions.length; k++) {
                                                        var opt = allOptions[k];
                                                        var optImage = opt.querySelector('.styled__ImageContent-eNVTVI, .styled__ImageContent, img');
                                                        if (optImage) {
                                                            var optImageSrc = optImage.src || optImage.getAttribute('src') || optImage.style.backgroundImage;
                                                            var imageSrc = imageContent.src || imageContent.getAttribute('src') || imageContent.style.backgroundImage;
                                                            if (optImageSrc && imageSrc && optImageSrc === imageSrc) {
                                                                var valueToSet = String(k + 1);
                                                                inputInArea.value = valueToSet;
                                                                Object.defineProperty(inputInArea, 'value', {
                                                                    value: valueToSet,
                                                                    writable: true,
                                                                    configurable: true
                                                                });
                                                                inputInArea.dispatchEvent(new Event('input', { bubbles: true, cancelable: true }));
                                                                inputInArea.dispatchEvent(new Event('change', { bubbles: true, cancelable: true }));
                                                                console.log('✓ Найдено и установлено значение для поля', index, ':', valueToSet);
                                                                break;
                                                            }
                                                        }
                                                    }
                                                }
                                            }
                                            break;
                                        }
                                    }
                                }
                            }
                        });
                        
                        // Инициируем события на форме
                        form.dispatchEvent(new Event('change', { bubbles: true, cancelable: true }));
                        form.dispatchEvent(new Event('input', { bubbles: true, cancelable: true }));
                        
                        // Обновляем все скрытые input поля формы
                        var allHiddenInputs = form.querySelectorAll('input[type="hidden"]');
                        allHiddenInputs.forEach(function(input) {
                            input.dispatchEvent(new Event('change', { bubbles: true }));
                            input.dispatchEvent(new Event('input', { bubbles: true }));
                        });
                        
                        console.log('=== ФИНАЛЬНОЕ ОБНОВЛЕНИЕ ЗАВЕРШЕНО ===');
                    }
                """, task_form)
                time.sleep(0.3)
            except Exception as final_update_error:
                print(f"  ⚠ Ошибка при финальном обновлении полей: {final_update_error}")
        
        print(f"  ✓ Выполнено перетаскиваний: {matched_count}")
        
        # ВАЖНО: После всех перетаскиваний создаем/обновляем все скрытые поля с правильными ID изображений
        if matched_count > 0 and has_images:
            try:
                time.sleep(0.5)  # Даем время DOM обновиться
                task_form = get_task_form(driver)
                driver.execute_script("""
                    var form = arguments[0];
                    if (form) {
                        console.log('=== СОЗДАНИЕ/ОБНОВЛЕНИЕ ВСЕХ СКРЫТЫХ ПОЛЕЙ ===');
                        
                        // Находим все drop areas
                        var dropAreas = form.querySelectorAll('.LinkTaskRow_linkRowContent__XBn6u');
                        console.log('Найдено drop areas:', dropAreas.length);
                        
                        // Находим все существующие скрытые поля
                        var allInputs = form.querySelectorAll('input[type="hidden"][name*="questions"]');
                        console.log('Найдено существующих скрытых полей:', allInputs.length);
                        
                        // Получаем questionId из первого поля
                        var questionId = null;
                        if (allInputs.length > 0) {
                            var firstInput = allInputs[0];
                            var match = firstInput.name.match(/questions\[(\d+)\]/);
                            if (match) {
                                questionId = match[1];
                            }
                        }
                        
                        if (!questionId) {
                            console.log('⚠ Не удалось определить questionId');
                            return;
                        }
                        
                        // Находим ID изображений в панели опций (в исходном порядке)
                        // Создаем маппинг: класс изображения -> ID
                        var optionsPanel = form.querySelector('.Options_root__q5QuO, .Options_optionsRows__JttWG, .LinkTask_optionsPanel__GLzIR');
                        var imageClassToId = {}; // Маппинг класса изображения к ID
                        var imageOrder = []; // Порядок изображений по классам
                        
                        if (optionsPanel) {
                            var allOptions = optionsPanel.querySelectorAll('.OptionsSlide_image__nlliP, .styled__ImageOption-ftJQiu, [draggable="true"]');
                            for (var i = 0; i < allOptions.length; i++) {
                                var opt = allOptions[i];
                                var optImage = opt.querySelector('.styled__ImageContent-eNVTVI, .styled__ImageContent');
                                if (optImage) {
                                    var imageClass = optImage.className;
                                    var optId = opt.getAttribute('data-id') || 
                                               opt.querySelector('[data-id]')?.getAttribute('data-id') || '';
                                    
                                    // Если нет data-id, пробуем найти ID из других источников
                                    if (!optId) {
                                        // Пробуем найти ID из структуры или других атрибутов
                                        var parentId = opt.getAttribute('id') || opt.closest('[id]')?.getAttribute('id') || '';
                                        if (parentId && /^\d+$/.test(parentId)) {
                                            optId = parentId;
                                        }
                                    }
                                    
                                    if (imageClass) {
                                        imageClassToId[imageClass] = optId;
                                        imageOrder.push(imageClass);
                                    }
                                }
                            }
                        }
                        console.log('Маппинг классов изображений к ID:', imageClassToId);
                        console.log('Порядок изображений:', imageOrder);
                        
                        // Для каждой drop area находим изображение и его ID
                        // ВАЖНО: ID изображений могут быть в разных местах - проверяем все возможные источники
                        var dropAreaValues = [];
                        dropAreas.forEach(function(dropArea, index) {
                            var imageElement = dropArea.querySelector('.styled__ImageContent-eNVTVI, .styled__ImageContent');
                            if (imageElement) {
                                // Находим родительский draggable элемент
                                var draggableParent = imageElement.closest('[draggable="true"]') || 
                                                     imageElement.closest('.OptionsSlide_image__nlliP') ||
                                                     imageElement.closest('.styled__ImageOption-ftJQiu') ||
                                                     imageElement.closest('.LinkTaskRow_option__Iw-In');
                                
                                var imageId = null;
                                
                                if (draggableParent) {
                                    // Пробуем найти ID из data-id
                                    imageId = draggableParent.getAttribute('data-id') || 
                                             draggableParent.querySelector('[data-id]')?.getAttribute('data-id') || '';
                                    
                                    // Если нет data-id, ищем по классу изображения в панели опций
                                    if (!imageId && optionsPanel) {
                                        var imageClass = imageElement.className;
                                        var allOptions = optionsPanel.querySelectorAll('.OptionsSlide_image__nlliP, .styled__ImageOption-ftJQiu, [draggable="true"]');
                                        for (var j = 0; j < allOptions.length; j++) {
                                            var opt = allOptions[j];
                                            var optImage = opt.querySelector('.styled__ImageContent-eNVTVI, .styled__ImageContent');
                                            if (optImage && optImage.className === imageClass) {
                                                imageId = opt.getAttribute('data-id') || 
                                                         opt.querySelector('[data-id]')?.getAttribute('data-id') || '';
                                                if (imageId) break;
                                            }
                                        }
                                    }
                                    
                                    // Если все еще нет ID, пробуем найти по порядку в панели опций
                                    // Используем индекс изображения в исходном порядке (1-based)
                                    if (!imageId && optionsPanel) {
                                        var allOptions = optionsPanel.querySelectorAll('.OptionsSlide_image__nlliP, .styled__ImageOption-ftJQiu, [draggable="true"]');
                                        var imageClass = imageElement.className;
                                        for (var j = 0; j < allOptions.length; j++) {
                                            var opt = allOptions[j];
                                            var optImage = opt.querySelector('.styled__ImageContent-eNVTVI, .styled__ImageContent');
                                            if (optImage && optImage.className === imageClass) {
                                                // ID может быть вычислен на основе позиции или других факторов
                                                // Пробуем найти в существующих input полях
                                                if (allInputs.length > j) {
                                                    var existingValue = allInputs[j].value;
                                                    if (existingValue && /^\d+$/.test(existingValue)) {
                                                        imageId = existingValue;
                                                        break;
                                                    }
                                                }
                                            }
                                        }
                                    }
                                }
                                
                                // Если ID не найден, используем значение из существующего input или генерируем
                                if (!imageId && index < allInputs.length) {
                                    var existingValue = allInputs[idx].value;
                                    if (existingValue && /^\d+$/.test(existingValue)) {
                                        imageId = existingValue;
                                    }
                                }
                                
                                dropAreaValues.push({
                                    index: index,
                                    imageId: imageId
                                });
                                console.log('Drop area', index, ':', imageId || 'ID не найден');
                            } else {
                                dropAreaValues.push({
                                    index: index,
                                    imageId: null
                                });
                                console.log('⚠ Drop area', index, ': изображение не найдено');
                            }
                        });
                        
                        // Создаем или обновляем скрытые поля
                        dropAreaValues.forEach(function(item, idx) {
                            if (item.imageId) {
                                // Определяем имя поля (используем существующие имена или создаем новые)
                                var fieldName = null;
                                var fieldId = null;
                                
                                // Пробуем найти существующее поле по индексу
                                if (idx < allInputs.length) {
                                    var existingInput = allInputs[idx];
                                    fieldName = existingInput.name;
                                    var match = fieldName.match(/\[(\d+)\]$/);
                                    if (match) {
                                        fieldId = match[1];
                                    }
                                } else {
                                    // Создаем новое имя поля
                                    if (allInputs.length > 0) {
                                        var lastInput = allInputs[allInputs.length - 1];
                                        var lastMatch = lastInput.name.match(/\[(\d+)\]$/);
                                        if (lastMatch) {
                                            fieldId = String(parseInt(lastMatch[1]) + 1);
                                        } else {
                                            fieldId = '10009546'; // Fallback
                                        }
                                    } else {
                                        fieldId = '10009542'; // Первое поле
                                    }
                                    fieldName = 'questions[' + questionId + '][' + fieldId + ']';
                                }
                                
                                // Находим или создаем input
                                var input = null;
                                if (idx < allInputs.length) {
                                    input = allInputs[idx];
                                } else {
                                    // Создаем новый input
                                    input = document.createElement('input');
                                    input.type = 'hidden';
                                    input.name = fieldName;
                                    input.tabIndex = -1;
                                    
                                    // Вставляем в корень формы
                                    var linkRoot = form.querySelector('[class*="Link_root"]') || form.querySelector('div > div > div');
                                    if (linkRoot) {
                                        linkRoot.appendChild(input);
                                    } else {
                                        form.appendChild(input);
                                    }
                                    console.log('✓ Создан новый input:', fieldName);
                                }
                                
                                // Устанавливаем значение (ID изображения)
                                input.value = item.imageId;
                                Object.defineProperty(input, 'value', {
                                    value: item.imageId,
                                    writable: true,
                                    configurable: true
                                });
                                input.dispatchEvent(new Event('input', { bubbles: true, cancelable: true }));
                                input.dispatchEvent(new Event('change', { bubbles: true, cancelable: true }));
                                console.log('✓ Установлено значение для', fieldName, ':', item.imageId);
                            }
                        });
                        
                        // Инициируем события на форме
                        form.dispatchEvent(new Event('change', { bubbles: true, cancelable: true }));
                        form.dispatchEvent(new Event('input', { bubbles: true, cancelable: true }));
                        
                        console.log('=== СОЗДАНИЕ/ОБНОВЛЕНИЕ ЗАВЕРШЕНО ===');
                    }
                """, task_form)
                print("  ✓ Все скрытые поля созданы/обновлены с правильными ID изображений")
            except Exception as e:
                print(f"  ⚠ Ошибка при создании/обновлении скрытых полей: {e}")
        
        return matched_count > 0
        
    except Exception as e:
        print(f"  ⚠ Ошибка при обработке drag and drop задачи: {e}")
        import traceback
        traceback.print_exc()
        return False

def handle_code_task(driver, code):
    """Обрабатывает задачу типа code (написание кода)
    code - строка с кодом для ввода
    
    Поддерживает два типа форм:
    1. Пустая форма (нужно написать код с нуля)
    2. Форма с начальным кодом (нужно изменить существующий код)"""
    try:
        task_form = get_task_form(driver)
        
        print("  Вводим код в редактор...")
        
        # Ищем CodeMirror редактор в Main панели
        # CodeMirror 6 использует класс cm-editor
        code_editor = None
        code_textarea = None
        
        # Сначала пробуем найти textarea (может быть скрытый)
        try:
            code_textarea = task_form.find_element(By.CSS_SELECTOR, "textarea[name*='source_code']")
        except:
            pass
        
        # Ищем редактор в Main панели через XPath
        try:
            # Ищем панель Main по тексту заголовка
            main_panel = task_form.find_element(By.XPATH, ".//div[contains(@class, 'styled__PanelHeader') and contains(text(), 'Main')]/following-sibling::div[contains(@class, 'styled__PanelContent')]")
            code_editor = main_panel.find_element(By.CSS_SELECTOR, ".cm-editor")
        except:
            # Если не нашли через XPath, пробуем найти любой cm-editor в форме
            try:
                code_editor = task_form.find_element(By.CSS_SELECTOR, ".cm-editor[data-language='python']")
            except:
                try:
                    # Пробуем найти первый cm-editor
                    code_editor = task_form.find_element(By.CSS_SELECTOR, ".cm-editor")
                except:
                    pass
        
        # Прокручиваем к найденному элементу
        if code_editor:
            driver.execute_script("arguments[0].scrollIntoView({block: 'center'});", code_editor)
            time.sleep(0.3)
        elif code_textarea:
            driver.execute_script("arguments[0].scrollIntoView({block: 'center'});", code_textarea)
            time.sleep(0.3)
        
        if not code_editor and not code_textarea:
            print("  ⚠ Не удалось найти CodeMirror редактор или textarea")
            return False
        
        # Вводим код - сначала пробуем через textarea (если он есть и редактируемый)
        # затем через CodeMirror API
        success = driver.execute_script("""
            var code = arguments[0];
            var editor = arguments[1];
            var textarea = arguments[2];
            
            try {
                // ПРИОРИТЕТ 1: Если есть textarea, обновляем его напрямую
                // CodeMirror должен автоматически синхронизироваться с textarea
                if (textarea) {
                    // Удаляем атрибут readonly, если он есть
                    textarea.removeAttribute('readonly');
                    
                    // Очищаем и устанавливаем значение
                    textarea.value = code;
                    
                    // Инициируем события для синхронизации с CodeMirror
                    var inputEvent = new Event('input', { bubbles: true, cancelable: true });
                    textarea.dispatchEvent(inputEvent);
                    
                    var changeEvent = new Event('change', { bubbles: true, cancelable: true });
                    textarea.dispatchEvent(changeEvent);
                    
                    // Также пробуем вызвать событие через свойство value (для некоторых редакторов)
                    Object.getOwnPropertyDescriptor(HTMLTextAreaElement.prototype, 'value').set.call(textarea, code);
                    textarea.dispatchEvent(new Event('input', { bubbles: true }));
                    
                    return true;
                }
                
                // ПРИОРИТЕТ 2: Работаем с CodeMirror 6 напрямую
                if (editor) {
                    // Пробуем найти view через различные способы
                    var view = editor.__cm_view || editor.cmView;
                    
                    // Если не нашли, пробуем через глобальный объект
                    if (!view && window.CodeMirror && window.CodeMirror.findEditor) {
                        view = window.CodeMirror.findEditor(editor);
                    }
                    
                    if (view && view.dispatch) {
                        // CodeMirror 6 API - используем dispatch для обновления
                        var state = view.state;
                        var transaction = state.update({
                            changes: {
                                from: 0,
                                to: state.doc.length,
                                insert: code
                            }
                        });
                        view.dispatch(transaction);
                        return true;
                    }
                }
                
                // ПРИОРИТЕТ 3: CodeMirror 5 API (старый)
                if (editor && editor.CodeMirror) {
                    editor.CodeMirror.setValue(code);
                    return true;
                }
                
                // ПРИОРИТЕТ 4: Ищем CodeMirror через textarea
                if (textarea) {
                    var cmElement = textarea.nextElementSibling;
                    if (cmElement && cmElement.CodeMirror) {
                        cmElement.CodeMirror.setValue(code);
                        return true;
                    }
                }
                
                // ПРИОРИТЕТ 5: Работаем напрямую с contenteditable элементом (CodeMirror 6)
                var contentEditable = editor ? editor.querySelector('.cm-content') : null;
                if (contentEditable) {
                    // Очищаем содержимое
                    contentEditable.innerHTML = '';
                    
                    // Разбиваем код на строки и создаем div для каждой строки
                    var lines = code.split('\\n');
                    if (lines.length === 0) lines = [''];
                    
                    lines.forEach(function(line, index) {
                        var lineDiv = document.createElement('div');
                        lineDiv.className = index === 0 ? 'cm-line cm-activeLine' : 'cm-line';
                        lineDiv.textContent = line;
                        contentEditable.appendChild(lineDiv);
                    });
                    
                    // Инициируем события
                    var inputEvent = new Event('input', { bubbles: true, cancelable: true });
                    contentEditable.dispatchEvent(inputEvent);
                    
                    var changeEvent = new Event('change', { bubbles: true, cancelable: true });
                    contentEditable.dispatchEvent(changeEvent);
                    
                    return true;
                }
                
                return false;
            } catch (e) {
                console.error('Ошибка при вводе кода:', e);
                return false;
            }
        """, code, code_editor, code_textarea)
        
        if success:
            print("  ✓ Код введен")
            time.sleep(0.5)
            
            # Дополнительно обновляем скрытый textarea, если он есть
            try:
                if code_textarea:
                    driver.execute_script("""
                        var textarea = arguments[0];
                        var code = arguments[1];
                        textarea.value = code;
                        textarea.dispatchEvent(new Event('input', { bubbles: true }));
                        textarea.dispatchEvent(new Event('change', { bubbles: true }));
                    """, code_textarea, code)
            except:
                pass
            
            return True
        else:
            print("  ⚠ Не удалось ввести код через CodeMirror API")
            return False
        
    except Exception as e:
        print(f"  ⚠ Ошибка при обработке code задачи: {e}")
        import traceback
        traceback.print_exc()
        return False

def handle_text_task(driver, answer):
    """Обрабатывает задачу типа text (текстовый ввод)
    answer - строка с ответом"""
    try:
        task_form = get_task_form(driver)
        
        # Находим текстовое поле
        text_input = task_form.find_element(By.CSS_SELECTOR, "input[type='text'][name*='questions']")
        
        print(f"  Вводим текст: '{answer}'")
        
        # Прокручиваем к полю ввода
        driver.execute_script("arguments[0].scrollIntoView({block: 'center'});", text_input)
        time.sleep(0.2)
        
        # Очищаем и вводим текст
        text_input.clear()
        text_input.send_keys(answer)
        
        print("  ✓ Текст введен")
        time.sleep(0.5)
        
        return True
        
    except Exception as e:
        print(f"  ⚠ Ошибка при обработке text задачи: {e}")
        return False

def parse_task_from_html(driver):
    """Парсит HTML страницы задачи и извлекает описание и варианты ответов
    Возвращает словарь с полями: description, options (список вариантов), task_type"""
    try:
        task_form = get_task_form(driver)
        
        # Извлекаем описание задачи из #taskContentInTaskContainer
        description = None
        try:
            # Ищем контейнер с описанием задачи
            task_content = driver.find_element(By.ID, "taskContentInTaskContainer")
            # Извлекаем текст из всех параграфов внутри
            paragraphs = task_content.find_elements(By.TAG_NAME, "p")
            if paragraphs:
                # Объединяем все параграфы в одно описание
                description_parts = [p.text.strip() for p in paragraphs if p.text.strip()]
                description = "\n".join(description_parts)
            else:
                # Если нет параграфов, берем весь текст контейнера
                description = task_content.text.strip()
        except Exception as e:
            print(f"  [DEBUG] Ошибка при извлечении описания из taskContentInTaskContainer: {e}")
            # Fallback: пробуем найти описание в других местах
            try:
                description_elements = driver.find_elements(By.XPATH, "//div[@id='taskContentInTaskContainer']//p")
                if description_elements:
                    description = description_elements[0].text.strip()
            except:
                pass
        
        if not description:
            print("  ⚠ Не удалось извлечь описание задачи")
        
        # Определяем тип задачи
        task_type = detect_task_type(driver)
        
        # Извлекаем варианты ответов в зависимости от типа задачи
        options = []
        
        if task_type == "radio":
            radios = task_form.find_elements(By.CSS_SELECTOR, "input[type='radio']")
            print(f"  [DEBUG] Найдено radio кнопок: {len(radios)}")
            for radio in radios:
                try:
                    value = radio.get_attribute("value")
                    # Извлекаем текст варианта из span.MathContent_content__2a8XE
                    label_text = None
                    try:
                        # Для контрольных заданий текст в span.MathContent_content__2a8XE
                        # Находим родительский div.styled__Root-jGVGzp, затем ищем span внутри
                        parent_root = radio.find_element(By.XPATH, "./ancestor::div[contains(@class, 'styled__Root-jGVGzp')][1]")
                        span = parent_root.find_element(By.CSS_SELECTOR, "span.MathContent_content__2a8XE")
                        label_text = span.text.strip()
                    except:
                        try:
                            # Альтернативный способ: ищем следующий sibling div
                            label_div = radio.find_element(By.XPATH, "./following-sibling::div[contains(@class, 'styled__Label')]")
                            span = label_div.find_element(By.CSS_SELECTOR, "span.MathContent_content__2a8XE")
                            label_text = span.text.strip()
                        except:
                            try:
                                label_div = radio.find_element(By.XPATH, "./following-sibling::div")
                                label_text = label_div.text.strip()
                            except:
                                parent = radio.find_element(By.XPATH, "./..")
                                label_text = parent.text.strip()
                    
                    if label_text:
                        options.append({
                            "value": value,
                            "text": label_text
                        })
                        print(f"  [DEBUG] Вариант {len(options)}: value={value}, text='{label_text[:50]}...'")
                except Exception as e:
                    print(f"  [DEBUG] Ошибка при извлечении варианта: {e}")
                    continue
        
        elif task_type == "checkbox":
            checkboxes = task_form.find_elements(By.CSS_SELECTOR, "input[type='checkbox']")
            print(f"  [DEBUG] Найдено checkbox кнопок: {len(checkboxes)}")
            for checkbox in checkboxes:
                try:
                    value = checkbox.get_attribute("value")
                    # Извлекаем текст варианта (аналогично radio)
                    label_text = None
                    try:
                        parent_root = checkbox.find_element(By.XPATH, "./ancestor::div[contains(@class, 'styled__Root-jGVGzp')][1]")
                        span = parent_root.find_element(By.CSS_SELECTOR, "span.MathContent_content__2a8XE")
                        label_text = span.text.strip()
                    except:
                        try:
                            label_div = checkbox.find_element(By.XPATH, "./following-sibling::div[contains(@class, 'styled__Label')]")
                            span = label_div.find_element(By.CSS_SELECTOR, "span.MathContent_content__2a8XE")
                            label_text = span.text.strip()
                        except:
                            try:
                                label_div = checkbox.find_element(By.XPATH, "./following-sibling::div")
                                label_text = label_div.text.strip()
                            except:
                                parent = checkbox.find_element(By.XPATH, "./..")
                                label_text = parent.text.strip()
                    
                    if label_text:
                        options.append({
                            "value": value,
                            "text": label_text
                        })
                except Exception as e:
                    print(f"  [DEBUG] Ошибка при извлечении варианта: {e}")
                    continue
        
        return {
            "description": description,
            "options": options,
            "task_type": task_type
        }
        
    except Exception as e:
        print(f"  ⚠ Ошибка при парсинге задачи из HTML: {e}")
        import traceback
        traceback.print_exc()
        return None

def get_answer_from_openrouter(task_data, api_key=None, model=None):
    """Отправляет задачу в OpenRouter API и получает ответ
    task_data - словарь с полями: description, options, task_type
    Возвращает ответ в формате, подходящем для handle_task"""
    try:
        if not api_key:
            api_key = OPENROUTER_API_KEY
        
        if not api_key:
            print("  ⚠ OpenRouter API ключ не установлен!")
            print("  Установите переменную окружения OPENROUTER_API_KEY или передайте ключ в функцию")
            return None
        
        if not model:
            model = OPENROUTER_MODEL
        
        # Формируем промпт для модели
        description = task_data.get('description', 'Не указано')
        options = task_data.get('options', [])
        
        prompt = f"""Ты эксперт по программированию и машинному обучению. Ответь на следующий вопрос, выбрав правильный вариант ответа.

Вопрос:
{description}

Варианты ответов:"""
        
        for i, option in enumerate(options, 1):
            option_text = option.get('text', '')
            prompt += f"\n{i}. {option_text}"
        
        prompt += """

ВАЖНО: Ответь ТОЛЬКО полным текстом выбранного варианта ответа, используя точно такой же текст, как в одном из вариантов выше. Не добавляй никаких объяснений, номеров или дополнительного текста. Просто скопируй текст выбранного варианта ответа."""
        
        # Отправляем запрос в OpenRouter API
        headers = {
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
            "HTTP-Referer": "https://github.com/your-repo",  # Опционально
            "X-Title": "Course Automation"  # Опционально
        }
        
        payload = {
            "model": model,
            "messages": [
                {
                    "role": "user",
                    "content": prompt
                }
            ],
            "temperature": 0.1,  # Низкая температура для более точных ответов
            "max_tokens": 500
        }
        
        print(f"  Отправляем запрос в OpenRouter API (модель: {model})...")
        response = requests.post(OPENROUTER_API_URL, headers=headers, json=payload, timeout=30)
        
        if response.status_code == 200:
            result = response.json()
            answer_text = result['choices'][0]['message']['content'].strip()
            print(f"  ✓ Получен ответ от модели: '{answer_text[:100]}...'")
            return answer_text
        else:
            print(f"  ⚠ Ошибка API: {response.status_code}")
            print(f"  Ответ: {response.text}")
            return None
            
    except Exception as e:
        print(f"  ⚠ Ошибка при запросе к OpenRouter API: {e}")
        import traceback
        traceback.print_exc()
        return None

def handle_randomized_task_with_ai(driver, api_key=None, model=None):
    """Обрабатывает рандомизированную задачу с помощью AI
    Парсит HTML, отправляет в OpenRouter API, получает ответ и заполняет форму
    Возвращает True если задача обработана успешно, False если ошибка, "homework_completed" если все задачи завершены"""
    try:
        print("\n  [AI] Обрабатываем рандомизированную задачу с помощью AI...")
        
        # Сохраняем текущий URL перед обработкой
        url_before = driver.current_url
        
        # Парсим задачу из HTML
        task_data = parse_task_from_html(driver)
        if not task_data:
            print("  ⚠ Не удалось распарсить задачу из HTML")
            return False
        
        if not task_data.get('description'):
            print("  ⚠ Описание задачи не найдено")
            return False
        
        if not task_data.get('options') or len(task_data.get('options', [])) == 0:
            print("  ⚠ Варианты ответов не найдены")
            return False
        
        print(f"  [AI] Описание задачи: {task_data.get('description', 'Не найдено')[:100]}...")
        print(f"  [AI] Тип задачи: {task_data.get('task_type')}")
        print(f"  [AI] Найдено вариантов: {len(task_data.get('options', []))}")
        
        # Выводим варианты для отладки
        for i, option in enumerate(task_data.get('options', []), 1):
            print(f"    {i}. {option.get('text', '')[:80]}...")
        
        # Получаем ответ от AI
        answer_text = get_answer_from_openrouter(task_data, api_key, model)
        if not answer_text:
            print("  ⚠ Не удалось получить ответ от AI")
            return False
        
        print(f"  [AI] Ответ от модели: '{answer_text}'")
        
        # Обрабатываем задачу с полученным ответом
        task_type = task_data.get('task_type')
        
        if task_type == "radio":
            # Для radio используем текст ответа для поиска соответствующего варианта
            result = handle_task(driver, answer_text)
        elif task_type == "checkbox":
            # Для checkbox нужно распарсить ответ (может быть несколько вариантов)
            # Пока обрабатываем как один вариант
            result = handle_task(driver, answer_text)
        else:
            print(f"  ⚠ Неподдерживаемый тип задачи для AI: {task_type}")
            return False
        
        # Проверяем, что мы перешли на следующую задачу или завершили все задачи
        if result == "homework_completed":
            return "homework_completed"
        elif result:
            # Проверяем, изменился ли URL (это означает, что мы перешли на следующую задачу)
            time.sleep(1)
            url_after = driver.current_url
            if url_after != url_before:
                print(f"  [AI] Перешли на следующую задачу: {url_after}")
                return True
            else:
                # URL не изменился - возможно, это была последняя задача или нужно нажать "Далее"
                print("  [AI] URL не изменился после обработки задачи")
                return True  # Возвращаем True, чтобы продолжить обработку
        
        return result
        
    except Exception as e:
        print(f"  ⚠ Ошибка при обработке рандомизированной задачи с AI: {e}")
        import traceback
        traceback.print_exc()
        return False

def submit_task_form(driver):
    """Отправляет форму задачи (нажимает кнопку 'Ответить') и затем кнопку 'Дальше'
    Если задача уже решена и нет кнопки submit, сразу ищет кнопку 'Дальше'"""
    try:
        task_form = get_task_form(driver)
        
        # Проверяем, есть ли кнопка отправки
        submit_button = None
        try:
            submit_button = task_form.find_element(By.CSS_SELECTOR, "button[type='submit']")
        except:
            print("  Кнопка 'Ответить' не найдена (возможно, задача уже решена)")
        
        # Для контрольных заданий проверяем кнопку с id="training-task-page-make-answer"
        # Она может быть как кнопкой "Ответить", так и "Далее" в зависимости от состояния
        training_button = None
        try:
            training_button = driver.find_element(By.ID, "training-task-page-make-answer")
            # Проверяем текст кнопки
            button_text = training_button.text.strip().lower()
            if "ответить" in button_text or "submit" in button_text or not button_text:
                # Это кнопка "Ответить"
                submit_button = training_button
                print("  Найдена кнопка 'Ответить' для контрольного задания")
        except:
            pass
        
        if submit_button:
            # Проверяем, что хотя бы одна радио-кнопка выбрана (если это radio задача)
            try:
                radios = task_form.find_elements(By.CSS_SELECTOR, "input[type='radio']")
                if radios:
                    selected_radios = [r for r in radios if r.is_selected()]
                    if not selected_radios:
                        # Проверяем через JS
                        selected_radios = [r for r in radios if driver.execute_script("return arguments[0].checked;", r)]
                    if not selected_radios:
                        print("  ⚠ ВНИМАНИЕ: Ни одна радио-кнопка не выбрана! Пробуем выбрать первую найденную...")
                        # Пробуем выбрать первую радио-кнопку (на случай, если выбор не сработал)
                        try:
                            first_radio = radios[0]
                            driver.execute_script("arguments[0].checked = true;", first_radio)
                            driver.execute_script("arguments[0].dispatchEvent(new Event('change'));", first_radio)
                            time.sleep(0.2)
                        except:
                            pass
                    else:
                        print(f"  ✓ Радио-кнопка выбрана (value: {selected_radios[0].get_attribute('value')})")
            except:
                pass
            
            print("  Нажимаем кнопку 'Ответить'...")
            
            # Прокручиваем к кнопке
            driver.execute_script("arguments[0].scrollIntoView({block: 'center'});", submit_button)
            time.sleep(0.3)
            
            # Кликаем на кнопку
            try:
                submit_button.click()
                print("  ✓ Кликнули на кнопку 'Ответить'")
            except Exception as e:
                print(f"  ⚠ Ошибка при клике на кнопку: {e}, пробуем через JS...")
                driver.execute_script("arguments[0].click();", submit_button)
                print("  ✓ Кликнули на кнопку 'Ответить' через JS")
            
            print("  ✓ Форма отправлена, ждем появления кнопки 'Дальше'...")
            time.sleep(0.5)  # Уменьшено время ожидания для обработки формы
        else:
            print("  Задача уже решена, ищем кнопку 'Дальше'...")
            time.sleep(0.3)  # Небольшая задержка для стабильности
        
        # Ищем кнопку "Дальше" или "Далее"
        # Если кнопка не найдена - это последний вопрос домашнего задания
        wait = WebDriverWait(driver, 1)  # Уменьшено время ожидания до 1 секунды
        try:
            # Ищем кнопку "Дальше" по нескольким способам
            next_button = None
            
            # Способ 0: Для контрольных заданий - кнопка с id="training-task-page-make-answer"
            # ВАЖНО: Эта кнопка сначала "Ответить", а после отправки формы становится "Далее"
            # Проверяем текст кнопки, чтобы убедиться, что это действительно "Далее"
            try:
                # Ждем, пока кнопка изменится на "Далее" после отправки формы
                wait_for_next = WebDriverWait(driver, 3)
                training_button = wait_for_next.until(
                    lambda d: (
                        btn := d.find_element(By.ID, "training-task-page-make-answer"),
                        btn if ("далее" in btn.text.strip().lower() or "next" in btn.text.strip().lower()) else None
                    )[1]
                )
                if training_button:
                    next_button = training_button
                    print("  Найдена кнопка 'Далее' для контрольного задания по ID (текст: 'Далее')")
            except:
                # Если не удалось найти кнопку с текстом "Далее", пробуем просто найти кнопку
                # (возможно, она уже изменилась или имеет другой текст)
                try:
                    training_button = driver.find_element(By.ID, "training-task-page-make-answer")
                    button_text = training_button.text.strip().lower()
                    # Проверяем, что это НЕ кнопка "Ответить"
                    if "ответить" not in button_text and "submit" not in button_text:
                        next_button = training_button
                        print(f"  Найдена кнопка для контрольного задания по ID (текст: '{training_button.text.strip()}')")
                except:
                    pass
            
            # Способ 1: По ссылке с классом styled__Root-ebtVmd и href /tasks/
            try:
                # Сначала пробуем быстрый поиск без ожидания
                next_button = driver.find_element(
                    By.XPATH,
                    "//a[contains(@class, 'styled__Root-ebtVmd') and contains(@href, '/tasks/')]"
                )
                print("  Найдена кнопка 'Дальше' по ссылке с классом")
            except:
                # Если не найдено, пробуем с ожиданием
                try:
                    next_button = wait.until(EC.element_to_be_clickable((
                        By.XPATH,
                        "//a[contains(@class, 'styled__Root-ebtVmd') and contains(@href, '/tasks/')]"
                    )))
                    print("  Найдена кнопка 'Дальше' по ссылке с классом (с ожиданием)")
                except:
                    pass
            
            # Способ 2: По тексту "Дальше" внутри правильной структуры
            if not next_button:
                try:
                    # Сначала пробуем быстрый поиск
                    text_div = driver.find_element(
                        By.XPATH,
                        "//div[contains(@class, 'styled__ButtonNext')]//div[contains(text(), 'Дальше')]"
                    )
                    next_button = text_div.find_element(By.XPATH, "./ancestor::a[contains(@class, 'styled__Root-ebtVmd')][1]")
                    print("  Найдена кнопка 'Дальше' по тексту")
                except:
                    # Если не найдено, пробуем с ожиданием
                    try:
                        text_div = wait.until(EC.presence_of_element_located((
                            By.XPATH,
                            "//div[contains(@class, 'styled__ButtonNext')]//div[contains(text(), 'Дальше')]"
                        )))
                        next_button = text_div.find_element(By.XPATH, "./ancestor::a[contains(@class, 'styled__Root-ebtVmd')][1]")
                        print("  Найдена кнопка 'Дальше' по тексту (с ожиданием)")
                    except:
                        pass
            
            # Способ 3: По ссылке с классом
            if not next_button:
                try:
                    # Сначала пробуем быстрый поиск
                    next_button = driver.find_element(By.CSS_SELECTOR, "a.fox-Anchor.styled__Root-ebtVmd")
                    print("  Найдена кнопка 'Дальше' по ссылке")
                except:
                    # Если не найдено, пробуем с ожиданием
                    try:
                        next_button = wait.until(EC.element_to_be_clickable((
                            By.CSS_SELECTOR,
                            "a.fox-Anchor.styled__Root-ebtVmd"
                        )))
                        print("  Найдена кнопка 'Дальше' по ссылке (с ожиданием)")
                    except:
                        pass
            
            # Способ 4: По href, содержащему /tasks/
            if not next_button:
                try:
                    # Сначала пробуем быстрый поиск
                    next_button = driver.find_element(
                        By.XPATH,
                        "//a[contains(@href, '/tasks/') and .//div[contains(text(), 'Дальше')]]"
                    )
                    print("  Найдена кнопка 'Дальше' по href")
                except:
                    # Если не найдено, пробуем с ожиданием
                    try:
                        next_button = wait.until(EC.element_to_be_clickable((
                            By.XPATH,
                            "//a[contains(@href, '/tasks/') and .//div[contains(text(), 'Дальше')]]"
                        )))
                        print("  Найдена кнопка 'Дальше' по href (с ожиданием)")
                    except:
                        pass
            
            # Способ 5: По классу styled__ButtonNext и ссылке с href /tasks/
            if not next_button:
                try:
                    next_button = driver.find_element(
                        By.XPATH,
                        "//a[contains(@class, 'styled__Root-ebtVmd') and contains(@href, '/tasks/')]//div[contains(@class, 'styled__ButtonNext')]"
                    )
                    # Находим родительскую ссылку
                    next_button = next_button.find_element(By.XPATH, "./ancestor::a[1]")
                    print("  Найдена кнопка 'Дальше' по структуре")
                except:
                    pass
            
            if next_button:
                # Прокручиваем к кнопке
                driver.execute_script("arguments[0].scrollIntoView({block: 'center'});", next_button)
                time.sleep(0.3)
                
                # Сохраняем текущий URL перед переходом
                url_before = driver.current_url
                
                # Кликаем на кнопку
                try:
                    next_button.click()
                    print("  ✓ Нажата кнопка 'Дальше'")
                except:
                    driver.execute_script("arguments[0].click();", next_button)
                    print("  ✓ Нажата кнопка 'Дальше' (через JS)")
                
                # Ждем загрузки новой страницы - проверяем изменение URL или появление новой формы
                try:
                    # Ждем изменения URL или появления новой формы задачи
                    wait = WebDriverWait(driver, 2.0)
                    try:
                        # Ждем изменения URL (для контрольных заданий)
                        wait.until(lambda d: d.current_url != url_before)
                        print(f"  ✓ URL изменился: {url_before} -> {driver.current_url}")
                    except:
                        # Если URL не изменился, ждем появления новой формы задачи
                        # (старая форма должна исчезнуть и появиться новая)
                        try:
                            wait.until(EC.staleness_of(task_form))
                            print("  ✓ Старая форма исчезла, ждем новую...")
                        except:
                            pass
                    
                    # Ждем появления новой формы (поддерживаем как обычные, так и контрольные задания)
                    try:
                        # Пробуем найти форму по ID (обычные задания)
                        wait.until(EC.presence_of_element_located((By.ID, "taskForm")))
                        print("  ✓ Новая форма задачи загружена (обычное задание)")
                    except:
                        # Пробуем найти форму контрольного задания
                        try:
                            wait.until(EC.presence_of_element_located((By.XPATH, "//form[contains(@action, '/trainings/')]")))
                            print("  ✓ Новая форма задачи загружена (контрольное задание)")
                            
                            # Дополнительная проверка: для контрольных заданий убеждаемся, что кнопка "Далее" 
                            # изменилась обратно на "Ответить" (это означает, что новая задача загружена)
                            # Это предотвращает повторное нажатие кнопки "Далее" для уже загруженной задачи
                            try:
                                wait_for_answer_button = WebDriverWait(driver, 2)
                                answer_button = wait_for_answer_button.until(
                                    lambda d: (
                                        btn := d.find_element(By.ID, "training-task-page-make-answer"),
                                        btn if ("ответить" in btn.text.strip().lower() or "submit" in btn.text.strip().lower() or not btn.text.strip()) else None
                                    )[1]
                                )
                                if answer_button:
                                    print("  ✓ Кнопка изменилась обратно на 'Ответить' - новая задача загружена")
                            except:
                                # Если не удалось найти кнопку "Ответить", это нормально - возможно, задача уже решена
                                # или кнопка имеет другой текст
                                pass
                        except:
                            # Если ничего не найдено, просто ждем немного
                            time.sleep(0.5)
                    
                    # Дополнительная проверка: убеждаемся, что форма задачи обновилась
                    # Ждем немного, чтобы React успел обновить содержимое
                    time.sleep(0.3)
                except Exception as e:
                    # Fallback: ждем немного времени для загрузки
                    print(f"  [DEBUG] Ожидание загрузки: {e}")
                    time.sleep(0.5)
                
                return True
            else:
                # Кнопка "Дальше" не найдена - это последний вопрос домашнего задания
                print("  ⚠ Кнопка 'Дальше' не найдена - это последний вопрос домашнего задания")
                print("  Возвращаемся на страницу курса...")
                
                # Возвращаемся на страницу курса (определяем по текущему URL)
                current_url = driver.current_url
                # Извлекаем базовый URL курса из текущего URL
                match = re.search(r'(https://kb\.cifrium\.ru/teacher/courses/\d+)', current_url)
                if match:
                    course_base_url = match.group(1)
                    driver.get(course_base_url)
                else:
                    # Fallback на MAIN_PAGE_URL, если не удалось извлечь
                    driver.get(MAIN_PAGE_URL)
                time.sleep(3)  # Увеличиваем время ожидания для обновления статуса заданий
                print("  ✓ Вернулись на страницу курса")
                return "homework_completed"  # Специальное значение для обозначения завершения ДЗ
                
        except Exception as e:
            print(f"  ⚠ Ошибка при поиске/нажатии кнопки 'Дальше': {e}")
            return False
        
    except Exception as e:
        print(f"  ⚠ Ошибка при отправке формы: {e}")
        return False

def handle_task(driver, task_answer=None):
    """Главная функция для обработки задачи любого типа
    task_answer - словарь или объект с ответом в зависимости от типа задачи:
        - checkbox: список значений (value) для выбора
        - radio: значение (value) для выбора
        - drag_and_drop: словарь {текст_цели: текст_элемента} или список кортежей
        - code: строка с кодом
        - text: строка с текстом ответа
    """
    try:
        # Определяем тип задачи
        task_type = detect_task_type(driver)
        
        # Если задача уже решена, просто переходим к следующей
        if task_type == "solved":
            print("  ✓ Задача уже решена, переходим к следующей")
            # Пытаемся найти кнопку "Дальше" или "Next" для перехода к следующей задаче
            try:
                next_button = WebDriverWait(driver, 2).until(
                    EC.element_to_be_clickable((By.XPATH, "//button[contains(text(), 'Дальше') or contains(text(), 'Next')]"))
                )
                next_button.click()
                time.sleep(1.5)  # Ждем перехода к следующей задаче
                return True
            except:
                # Если кнопки нет, возможно это последняя задача или нужно вернуться на страницу задач
                # Проверяем, есть ли кнопка возврата или мы уже на странице задач
                try:
                    # Пробуем найти любую кнопку навигации
                    nav_button = driver.find_element(By.XPATH, "//button[contains(@class, 'button') or contains(@class, 'btn')]")
                    if nav_button:
                        nav_button.click()
                        time.sleep(1)
                except:
                    pass
                # Возвращаем True (задача уже решена, можно продолжать)
                return True
        
        if task_type == "unknown":
            print("  ⚠ Не удалось определить тип задачи, пропускаем")
            return False
        
        # Если ответ не предоставлен, просто сообщаем о типе
        if task_answer is None:
            print(f"  Тип задачи определен: {task_type}")
            print("  Ответ не предоставлен, задача не обработана")
            return False
        
        # Обрабатываем задачу в зависимости от типа
        success = False
        
        if task_type == "checkbox":
            if isinstance(task_answer, list):
                success = handle_checkbox_task(driver, task_answer)
            else:
                print("  ⚠ Для checkbox задачи нужен список значений")
        
        elif task_type == "radio":
            if isinstance(task_answer, str) or isinstance(task_answer, (int, float)):
                print(f"  [DEBUG] Вызываем handle_radio_task с answer: {task_answer} (тип: {type(task_answer)})")
                success = handle_radio_task(driver, str(task_answer))
                print(f"  [DEBUG] handle_radio_task вернул: {success}")
            else:
                print(f"  ⚠ Для radio задачи нужно одно значение, получено: {task_answer} (тип: {type(task_answer)})")
        
        elif task_type == "drag_and_drop":
            # Если ответ - это строка (не список кортежей и не словарь), возможно это на самом деле text задача
            if isinstance(task_answer, str):
                print("  Ответ для drag_and_drop - это строка, обрабатываем как text...")
                success = handle_text_task(driver, task_answer)
            elif isinstance(task_answer, (list, dict)):
                success = handle_drag_and_drop_task(driver, task_answer)
            else:
                print(f"  ⚠ Неожиданный тип ответа для drag_and_drop: {type(task_answer)}")
                success = False
        
        elif task_type == "code":
            if isinstance(task_answer, str):
                success = handle_code_task(driver, task_answer)
            else:
                print("  ⚠ Для code задачи нужна строка с кодом")
        
        elif task_type == "text":
            if isinstance(task_answer, str) or isinstance(task_answer, (int, float)):
                success = handle_text_task(driver, str(task_answer))
            else:
                print("  ⚠ Для text задачи нужна строка с текстом")
        
        # Отправляем форму после успешной обработки
        if success:
            print("  ✓ Задача обработана, отправляем форму...")
            submit_result = submit_task_form(driver)
            if submit_result == "homework_completed":
                print("  ✓ Домашнее задание завершено, возвращаемся на страницу курса")
                return "homework_completed"
            elif submit_result:
                print("  ✓ Форма отправлена и переход выполнен")
                return True
            else:
                print("  ⚠ Задача обработана, но возникла ошибка при отправке формы")
                return False
        else:
            print("  ⚠ Задача не была обработана")
            return False
            
    except Exception as e:
        print(f"  ⚠ Ошибка при обработке задачи: {e}")
        import traceback
        traceback.print_exc()
        return False

def strict_text_match(answer_text, label_text):
    """Строгое сопоставление текста ответа с текстом варианта
    Возвращает True если варианты совпадают, False в противном случае
    Приоритет: точное совпадение > полный ответ в варианте > частичное совпадение (только если >80%)"""
    # Нормализуем пробелы и приводим к нижнему регистру
    answer_normalized = ' '.join(answer_text.lower().split())
    label_normalized = ' '.join(label_text.lower().split())
    
    # 1. Точное совпадение (после нормализации)
    if answer_normalized == label_normalized:
        return True
    
    # 2. Полный ответ содержится в варианте (вариант длиннее или равен)
    # Это означает, что вариант содержит полный ответ, возможно с дополнительным текстом
    if len(label_normalized) >= len(answer_normalized):
        if answer_normalized in label_normalized:
            # Проверяем, что совпадение начинается с начала или имеет разумную границу
            if label_normalized.startswith(answer_normalized) or \
               label_normalized.endswith(answer_normalized) or \
               f' {answer_normalized} ' in f' {label_normalized} ':
                return True
    
    # 3. Вариант содержится в ответе, но только если это составляет значительную часть
    # (чтобы избежать выбора коротких усеченных вариантов)
    if len(answer_normalized) >= len(label_normalized):
        if label_normalized in answer_normalized:
            # Проверяем, что длина совпадения составляет не менее 80% от длины более короткой строки
            min_length = min(len(answer_normalized), len(label_normalized))
            match_length = len(label_normalized)
            if match_length >= min_length * 0.8:
                # Но только если это единственный такой вариант или если вариант начинается с ответа
                if answer_normalized.startswith(label_normalized):
                    return True
    
    # 4. Частичное совпадение с высоким процентом (для случаев с опечатками)
    # Вычисляем процент совпадения
    longer = answer_normalized if len(answer_normalized) > len(label_normalized) else label_normalized
    shorter = label_normalized if len(answer_normalized) > len(label_normalized) else answer_normalized
    
    # Если более короткая строка составляет более 80% более длинной и содержится в ней
    if len(shorter) >= len(longer) * 0.8 and shorter in longer:
        return True
    
    return False

def find_best_radio_match(answer_text, radios):
    """Находит наиболее подходящую радио-кнопку для ответа
    Возвращает (radio_element, value) или (None, None)
    Приоритет: точное совпадение > вариант содержит полный ответ (выбирается самый длинный) > частичное совпадение"""
    answer_normalized = ' '.join(answer_text.lower().split())
    
    # Собираем все варианты с их текстами
    candidates = []
    for radio in radios:
        try:
            # Пробуем несколько способов извлечения текста
            label_text = None
            
            # Способ 1: Ищем следующий sibling div с классом styled__Label или MathContent_root
            # Это соответствует структуре: <input type="radio"> <div class="styled__Label">...</div>
            if not label_text:
                try:
                    # Сначала пробуем найти span с точным классом MathContent_content__2a8XE в следующем sibling div
                    label_div = radio.find_element(By.XPATH, "./following-sibling::div[contains(@class, 'styled__Label') or contains(@class, 'MathContent_root')]")
                    try:
                        # Ищем span с точным классом MathContent_content__2a8XE
                        span = label_div.find_element(By.CSS_SELECTOR, "span.MathContent_content__2a8XE")
                        label_text = span.text.strip()
                    except:
                        try:
                            # Если не нашли, пробуем найти любой span с классом содержащим MathContent_content
                            span = label_div.find_element(By.XPATH, ".//span[contains(@class, 'MathContent_content')]")
                            label_text = span.text.strip()
                        except:
                            label_text = label_div.text.strip()
                except:
                    pass
            
            # Способ 1.5: Ищем span с классом MathContent_content__2a8XE (точный класс из HTML)
            if not label_text:
                try:
                    # Ищем следующий sibling div
                    label_div = radio.find_element(By.XPATH, "./following-sibling::div")
                    # Ищем span с точным классом MathContent_content__2a8XE
                    try:
                        span = label_div.find_element(By.CSS_SELECTOR, "span.MathContent_content__2a8XE")
                        label_text = span.text.strip()
                    except:
                        # Пробуем найти любой span с классом содержащим MathContent_content
                        try:
                            span = label_div.find_element(By.XPATH, ".//span[contains(@class, 'MathContent_content')]")
                            label_text = span.text.strip()
                        except:
                            label_text = label_div.text.strip()
                except:
                    pass
            
            # Способ 2: Ищем в родительском элементе div с классом styled__Label
            if not label_text:
                try:
                    parent = radio.find_element(By.XPATH, "./..")
                    label_div = parent.find_element(By.XPATH, ".//div[contains(@class, 'styled__Label') or contains(@class, 'MathContent_root')]")
                    try:
                        span = label_div.find_element(By.XPATH, ".//span[contains(@class, 'MathContent_content')]")
                        label_text = span.text.strip()
                    except:
                        label_text = label_div.text.strip()
                except:
                    pass
            
            # Способ 3: Ищем связанный label по атрибуту for
            if not label_text:
                radio_id = radio.get_attribute("id")
                if radio_id:
                    try:
                        label = radio.find_element(By.XPATH, f"//label[@for='{radio_id}']")
                        label_text = label.text.strip()
                    except:
                        pass
            
            # Способ 4: Ищем label, который содержит этот radio
            if not label_text:
                try:
                    label = radio.find_element(By.XPATH, "./ancestor::label[1]")
                    label_text = label.text.strip()
                except:
                    pass
            
            # Способ 5: Берем весь текст из родительского элемента (fallback)
            if not label_text:
                try:
                    parent = radio.find_element(By.XPATH, "./..")
                    label_text = parent.text.strip()
                except:
                    pass
            
            if not label_text:
                # Пробуем еще раз через родительский элемент
                try:
                    parent = radio.find_element(By.XPATH, "./..")
                    label_text = parent.text.strip()
                    if label_text:
                        # Убираем текст из других элементов (например, из других radio)
                        # Берем только текст из следующего sibling div
                        try:
                            next_div = radio.find_element(By.XPATH, "./following-sibling::div")
                            label_text = next_div.text.strip()
                        except:
                            pass
                except:
                    pass
            
            if not label_text:
                continue
                
            value = radio.get_attribute("value")
            label_normalized = ' '.join(label_text.lower().split())
            candidates.append((radio, value, label_text, label_normalized, len(label_normalized)))
        except:
            continue
    
    if not candidates:
        print(f"    [DEBUG] Не найдено кандидатов для радио-кнопок")
        return None, None
    
    # Выводим найденные варианты для отладки
    print(f"    [DEBUG] Найдено кандидатов: {len(candidates)}")
    for i, (radio, value, label_text, label_normalized, _) in enumerate(candidates[:5]):  # Показываем первые 5
        print(f"      {i+1}. value={value}, text='{label_text[:80]}...' (длина: {len(label_text)})")
    
    # Сортируем по длине (сначала самые длинные) для приоритета полных ответов
    candidates.sort(key=lambda x: x[4], reverse=True)
    
    print(f"    [DEBUG] Ищем совпадение для: '{answer_text[:100]}...' (нормализовано: '{answer_normalized[:100]}...', длина: {len(answer_normalized)})")
    
    # 1. Ищем точное совпадение
    for radio, value, label_text, label_normalized, _ in candidates:
        if answer_normalized == label_normalized:
            print(f"    [DEBUG] Найдено точное совпадение!")
            return radio, value
    
    # 1.2. Ищем почти идентичные тексты (разница в 1-5 символов)
    # Это важно, когда тексты почти совпадают, но могут отличаться на несколько символов
    for radio, value, label_text, label_normalized, _ in candidates:
        len_diff = abs(len(answer_normalized) - len(label_normalized))
        if len_diff <= 5:  # Разница не более 5 символов
            # Используем SequenceMatcher для более точного сравнения
            from difflib import SequenceMatcher
            similarity = SequenceMatcher(None, answer_normalized, label_normalized).ratio()
            if similarity >= 0.95:  # 95% совпадение
                print(f"    [DEBUG] Найдено почти идентичное совпадение (similarity: {similarity:.2%})")
                return radio, value
            # Также проверяем, начинаются ли они одинаково (первые 90% более короткой строки)
            min_len = min(len(answer_normalized), len(label_normalized))
            if min_len > 10:  # Только если строка достаточно длинная
                check_len = int(min_len * 0.90)
                if answer_normalized[:check_len] == label_normalized[:check_len]:
                    # Если первые 90% совпадают, это хорошее совпадение
                    print(f"    [DEBUG] Найдено совпадение по началу строки (первые {check_len} символов)")
                    return radio, value
    
    # 1.5. Ищем совпадение, где текст в Excel может быть обрезан
    # Если ответ из Excel короче, но вариант на странице начинается с ответа - это совпадение
    for radio, value, label_text, label_normalized, _ in candidates:
        if len(answer_normalized) < len(label_normalized):
            # Ответ из Excel может быть обрезан
            if label_normalized.startswith(answer_normalized):
                # Проверяем, что совпадение достаточно длинное (не менее 70% от варианта)
                match_ratio = len(answer_normalized) / len(label_normalized)
                if match_ratio >= 0.7:
                    print(f"    [DEBUG] Найдено совпадение: ответ из Excel обрезан, но вариант начинается с ответа")
                    return radio, value
        elif len(label_normalized) < len(answer_normalized):
            # Текст на странице может быть обрезан
            if answer_normalized.startswith(label_normalized):
                # Проверяем, что совпадение достаточно длинное (не менее 70% от ответа)
                match_ratio = len(label_normalized) / len(answer_normalized)
                if match_ratio >= 0.7:
                    print(f"    [DEBUG] Найдено совпадение: вариант на странице обрезан, но ответ начинается с варианта")
                    return radio, value
    
    # 2. Ищем вариант, где полный ответ содержится в варианте (вариант длиннее или равен)
    # Приоритет более длинным вариантам (они уже отсортированы)
    for radio, value, label_text, label_normalized, _ in candidates:
        if len(label_normalized) >= len(answer_normalized):
            # Проверяем, содержится ли ответ в варианте
            if answer_normalized in label_normalized:
                # Проверяем, что совпадение имеет разумную границу
                if label_normalized.startswith(answer_normalized) or \
                   label_normalized.endswith(answer_normalized) or \
                   f' {answer_normalized} ' in f' {label_normalized} ':
                    print(f"    [DEBUG] Найдено совпадение: ответ содержится в варианте")
                    return radio, value
            # Также проверяем обратное - вариант содержится в ответе (если они почти одинаковой длины)
            elif len(label_normalized) >= len(answer_normalized) * 0.95:  # Вариант не намного длиннее
                if label_normalized in answer_normalized:
                    print(f"    [DEBUG] Найдено совпадение: вариант содержится в ответе")
                    return radio, value
    
    # 2.5. Ищем совпадение по ключевым словам (если точное совпадение не найдено)
    # Извлекаем ключевые слова из ответа (слова длиннее 3 символов)
    answer_words = [w for w in answer_normalized.split() if len(w) > 3]
    if len(answer_words) >= 3:  # Только если есть достаточно ключевых слов
        best_match = None
        best_score = 0
        for radio, value, label_text, label_normalized, _ in candidates:
            # Считаем, сколько ключевых слов из ответа есть в варианте
            label_words = set(label_normalized.split())
            matching_words = sum(1 for word in answer_words if word in label_words)
            score = matching_words / len(answer_words)  # Процент совпадения ключевых слов
            
            # Если совпало более 70% ключевых слов, это хороший кандидат
            if score > best_score and score >= 0.7:
                best_match = (radio, value)
                best_score = score
        
        if best_match:
            print(f"    [DEBUG] Найдено совпадение по ключевым словам (score: {best_score:.2%})")
            return best_match[0], best_match[1]
    
    # 3. Ищем вариант, который содержится в ответе, но только если он составляет значительную часть
    # И только если нет варианта, который содержит полный ответ
    for radio, value, label_text, label_normalized, label_len in candidates:
        if len(answer_normalized) >= len(label_normalized):
            if label_normalized in answer_normalized:
                # Проверяем, что длина совпадения составляет не менее 90% от длины более короткой строки
                # Это более строгое требование, чтобы избежать выбора коротких усеченных вариантов
                match_ratio = len(label_normalized) / len(answer_normalized)
                if match_ratio >= 0.9 and answer_normalized.startswith(label_normalized):
                    # Но только если нет более длинного варианта, который тоже совпадает
                    # (мы уже отсортированы по длине, так что первый подходящий - самый длинный)
                    return radio, value
    
    # Если ничего не найдено, логируем для отладки
    print(f"    [DEBUG] Ответ из Excel (нормализованный): '{answer_normalized[:100]}...' (длина: {len(answer_normalized)})")
    print(f"    [DEBUG] Доступные варианты (первые 3):")
    for radio, value, label_text, label_normalized, label_len in candidates[:3]:
        print(f"      - '{label_text[:100]}...' (нормализованный: '{label_normalized[:100]}...', длина: {label_len})")
        # Проверяем, есть ли частичное совпадение
        if answer_normalized.startswith(label_normalized) or label_normalized.startswith(answer_normalized):
            overlap = min(len(answer_normalized), len(label_normalized))
            print(f"        [Частичное совпадение: первые {overlap} символов совпадают]")
    
    return None, None

def find_checkbox_matches(answer_parts, checkboxes):
    """Находит чекбоксы, соответствующие частям ответа
    Возвращает список значений (value)
    Использует строгую логику сопоставления с приоритетом более длинных вариантов"""
    selected_values = []
    
    # Собираем все чекбоксы с их данными
    checkbox_candidates = []
    for checkbox in checkboxes:
        try:
            label_text = None
            value = checkbox.get_attribute("value")
            
            # Способ 1: Ищем следующий sibling div с классом styled__Label или MathContent_root
            # Структура: <input> <div class="styled__Label"> <span class="MathContent_content">текст</span> </div>
            try:
                label_div = checkbox.find_element(By.XPATH, "./following-sibling::div[contains(@class, 'styled__Label') or contains(@class, 'MathContent_root')]")
                try:
                    # Сначала пробуем найти span с классом MathContent_content__2a8XE или MathContent_content
                    span = label_div.find_element(By.XPATH, ".//span[contains(@class, 'MathContent_content')]")
                    label_text = span.text.strip()
                except:
                    # Если span не найден, берем текст из div
                    label_text = label_div.text.strip()
            except:
                pass
            
            # Способ 2: Если не нашли, пробуем найти через XPath с более точным селектором
            if not label_text:
                try:
                    # Ищем div с классом, содержащим styled__Label, который является sibling input
                    label_div = checkbox.find_element(By.XPATH, "./following-sibling::div[contains(@class, 'styled__Label-iUCEmK') or contains(@class, 'MathContent_root')]")
                    # Внутри ищем span с MathContent_content
                    try:
                        span = label_div.find_element(By.CSS_SELECTOR, "span.MathContent_content__2a8XE, span[class*='MathContent_content']")
                        label_text = span.text.strip()
                    except:
                        label_text = label_div.text.strip()
                except:
                    pass
            
            # Способ 3: Если не нашли, пробуем родительский элемент
            if not label_text:
                try:
                    parent = checkbox.find_element(By.XPATH, "./..")
                    # В родителе ищем span с MathContent_content
                    try:
                        span = parent.find_element(By.CSS_SELECTOR, "span.MathContent_content__2a8XE, span[class*='MathContent_content']")
                        label_text = span.text.strip()
                    except:
                        label_text = parent.text.strip()
                except:
                    pass
            
            # Способ 4: Ищем label по id
            if not label_text:
                try:
                    label_id = checkbox.get_attribute("id")
                    if label_id:
                        label = checkbox.find_element(By.XPATH, f".//ancestor::form//label[@for='{label_id}']")
                        label_text = label.text.strip()
                except:
                    pass
            
            if label_text:
                # Нормализуем текст: приводим к нижнему регистру и убираем лишние пробелы
                label_normalized = ' '.join(label_text.lower().split())
                checkbox_candidates.append((value, label_text, label_normalized, len(label_normalized)))
        except Exception as e:
            print(f"    [DEBUG] Ошибка при извлечении текста чекбокса: {e}")
            continue
    
    print(f"    [DEBUG] Найдено кандидатов чекбоксов: {len(checkbox_candidates)}")
    for i, (value, label_text, label_normalized, _) in enumerate(checkbox_candidates[:5], 1):
        print(f"      {i}. value={value}, text='{label_text[:60]}...'")
    
    # Сортируем по длине (сначала самые длинные) для приоритета полных ответов
    checkbox_candidates.sort(key=lambda x: x[3], reverse=True)
    
    for answer_part in answer_parts:
        # Нормализуем ответ так же, как и варианты
        answer_normalized = ' '.join(answer_part.lower().split())
        print(f"    [DEBUG] Ищем совпадение для: '{answer_part}' (нормализовано: '{answer_normalized}')")
        best_match = None
        
        # Создаем версию с заменой похожих символов для более гибкого сравнения
        # Кириллическая 'і' и латинская 'i', кириллическая 'е' и латинская 'e'
        answer_normalized_flexible = answer_normalized.replace('і', 'i').replace('е', 'e')
        
        # 1. Ищем точное совпадение
        for value, label_text, label_normalized, _ in checkbox_candidates:
            if answer_normalized == label_normalized:
                print(f"    [DEBUG] Найдено точное совпадение!")
                best_match = value
                break
        
        # 2. Если точного совпадения нет, ищем вариант, где полный ответ содержится в варианте
        if not best_match:
            for value, label_text, label_normalized, _ in checkbox_candidates:
                if len(label_normalized) >= len(answer_normalized):
                    if answer_normalized in label_normalized:
                        # Проверяем, что совпадение имеет разумную границу
                        if label_normalized.startswith(answer_normalized) or \
                           label_normalized.endswith(answer_normalized) or \
                           f' {answer_normalized} ' in f' {label_normalized} ':
                            print(f"    [DEBUG] Найдено совпадение: ответ содержится в варианте")
                            best_match = value
                            break
        
        # 3. Если не нашли вариант с полным ответом, ищем частичное совпадение (>= 70%)
        if not best_match:
            for value, label_text, label_normalized, label_len in checkbox_candidates:
                if len(answer_normalized) >= len(label_normalized):
                    if label_normalized in answer_normalized:
                        match_ratio = len(label_normalized) / len(answer_normalized)
                        if match_ratio >= 0.7 and answer_normalized.startswith(label_normalized):
                            print(f"    [DEBUG] Найдено частичное совпадение (ratio: {match_ratio:.2%})")
                            best_match = value
                            break
                elif len(label_normalized) >= len(answer_normalized):
                    # Обратный случай - вариант длиннее ответа
                    if answer_normalized in label_normalized:
                        match_ratio = len(answer_normalized) / len(label_normalized)
                        if match_ratio >= 0.7 and label_normalized.startswith(answer_normalized):
                            print(f"    [DEBUG] Найдено частичное совпадение (обратное, ratio: {match_ratio:.2%})")
                            best_match = value
                            break
        
        # 4. Используем гибкое сравнение с заменой похожих символов
        if not best_match:
            label_normalized_flexible_map = {}
            for value, label_text, label_normalized, _ in checkbox_candidates:
                label_normalized_flexible = label_normalized.replace('і', 'i').replace('е', 'e')
                label_normalized_flexible_map[value] = label_normalized_flexible
                
                # Проверяем точное совпадение после замены символов
                if answer_normalized_flexible == label_normalized_flexible:
                    print(f"    [DEBUG] Найдено совпадение после замены похожих символов")
                    best_match = value
                    break
        
        # 5. Используем SequenceMatcher для более гибкого сравнения
        if not best_match:
            from difflib import SequenceMatcher
            best_similarity = 0.7
            for value, label_text, label_normalized, _ in checkbox_candidates:
                # Сначала пробуем обычное сравнение
                similarity = SequenceMatcher(None, answer_normalized, label_normalized).ratio()
                # Затем пробуем с заменой символов
                label_normalized_flexible = label_normalized.replace('і', 'i').replace('е', 'e')
                similarity_flexible = SequenceMatcher(None, answer_normalized_flexible, label_normalized_flexible).ratio()
                similarity = max(similarity, similarity_flexible)
                
                if similarity > best_similarity:
                    best_similarity = similarity
                    best_match = value
                    print(f"    [DEBUG] Найдено совпадение через SequenceMatcher (similarity: {similarity:.2%})")
        
        if best_match:
            if best_match not in selected_values:
                selected_values.append(best_match)
                # Находим текст для вывода
                for value, label_text, _, _ in checkbox_candidates:
                    if value == best_match:
                        print(f"    ✓ Найден чекбокс для '{answer_part[:50]}...': '{label_text[:50]}...' (value: {best_match})")
                        break
        else:
            print(f"    [DEBUG] Не найдено совпадение для: '{answer_part}'")
            print(f"    [DEBUG] Доступные варианты:")
            for value, label_text, label_normalized, _ in checkbox_candidates[:3]:
                print(f"      - value={value}: '{label_text[:60]}...' (нормализованный: '{label_normalized[:60]}...')")
    
    return selected_values

def parse_checkbox_answer(answer_text):
    """Парсит ответ для checkbox из формата массива строк в кавычках
    Формат: ["строка1", "строка2", "строка3"] или ["строка1"\n"строка2"]
    Возвращает список строк"""
    try:
        # Убираем пробелы в начале и конце
        answer_text = answer_text.strip()
        
        # Убираем квадратные скобки, если есть
        if answer_text.startswith('['):
            answer_text = answer_text[1:]
        if answer_text.endswith(']'):
            answer_text = answer_text[:-1]
        
        answer_text = answer_text.strip()
        
        # Парсим строки в кавычках
        # Используем регулярное выражение для поиска всех строк в кавычках
        # Поддерживаем как двойные, так и одинарные кавычки
        pattern = r'["\']([^"\']*)["\']'
        matches = re.findall(pattern, answer_text)
        
        if matches:
            # Очищаем каждую строку от пробелов
            result = [match.strip() for match in matches if match.strip()]
            return result
        
        # Если не нашли через регулярное выражение, пробуем разделить по запятым/переносам строк
        # и убрать кавычки вручную
        parts = re.split(r'[,;\n]\s*', answer_text)
        result = []
        for part in parts:
            part = part.strip()
            # Убираем кавычки в начале и конце
            if (part.startswith('"') and part.endswith('"')) or (part.startswith("'") and part.endswith("'")):
                part = part[1:-1]
            part = part.strip()
            if part:
                result.append(part)
        
        return result
        
    except Exception as e:
        print(f"    ⚠ Ошибка при парсинге ответа checkbox: {e}")
        # Fallback: просто разделяем по запятой
        return [s.strip().strip('"').strip("'") for s in answer_text.split(',') if s.strip()]

def parse_drag_and_drop_answer(answer_text):
    """Парсит ответ для drag and drop задачи
    Поддерживает форматы:
    1. JSON-объект: {"цель_1": "элемент_1", "цель_2": "элемент_2"}
    2. Список пар через разделитель: "цель_1 -> элемент_1; цель_2 -> элемент_2"
    3. Список кортежей: [("цель_1", "элемент_1"), ("цель_2", "элемент_2")]
    
    Возвращает список кортежей [(цель, элемент), ...]"""
    try:
        answer_text = answer_text.strip()
        
        # Формат 1: JSON-объект
        if answer_text.startswith('{') and answer_text.endswith('}'):
            try:
                mappings_dict = json.loads(answer_text)
                if isinstance(mappings_dict, dict):
                    result = list(mappings_dict.items())
                    print(f"    ✓ Успешно распарсен JSON-объект: {len(result)} сопоставлений")
                    return result
            except json.JSONDecodeError as e:
                print(f"    ⚠ Ошибка парсинга JSON: {e}")
                print(f"    Полный JSON (первые 500 символов): '{answer_text[:500]}...'")
                # Пробуем исправить JSON - находим правильный конец объекта по балансу скобок
                brace_count = 0
                last_valid_pos = -1
                for i, char in enumerate(answer_text):
                    if char == '{':
                        brace_count += 1
                    elif char == '}':
                        brace_count -= 1
                        if brace_count == 0:
                            last_valid_pos = i
                            break
                
                if last_valid_pos > 0:
                    cleaned_text = answer_text[:last_valid_pos + 1]
                    try:
                        mappings_dict = json.loads(cleaned_text)
                        if isinstance(mappings_dict, dict):
                            result = list(mappings_dict.items())
                            print(f"    ✓ Успешно распарсен JSON-объект (после очистки): {len(result)} сопоставлений")
                            return result
                    except Exception as e2:
                        print(f"    ⚠ Не удалось распарсить после очистки: {e2}")
                
                # Пробуем использовать регулярные выражения для извлечения пар ключ-значение
                try:
                    import re
                    # Улучшенный подход: парсим JSON вручную, находя правильные границы строк
                    # Ищем все пары "ключ": "значение", учитывая что кавычки внутри могут быть частью значения
                    result = []
                    i = 0
                    while i < len(answer_text):
                        # Ищем начало ключа
                        if answer_text[i] == '"':
                            # Находим конец ключа
                            key_start = i + 1
                            key_end = key_start
                            while key_end < len(answer_text) and answer_text[key_end] != '"':
                                if answer_text[key_end] == '\\':
                                    key_end += 2  # Пропускаем экранированный символ
                                else:
                                    key_end += 1
                            
                            if key_end < len(answer_text):
                                key = answer_text[key_start:key_end]
                                # Ищем двоеточие после ключа
                                colon_pos = answer_text.find(':', key_end + 1)
                                if colon_pos > 0:
                                    # Ищем начало значения
                                    value_start_pos = answer_text.find('"', colon_pos + 1)
                                    if value_start_pos > 0:
                                        value_start = value_start_pos + 1
                                        value_end = value_start
                                        # Находим конец значения (учитывая экранированные кавычки)
                                        while value_end < len(answer_text) and answer_text[value_end] != '"':
                                            if answer_text[value_end] == '\\':
                                                value_end += 2
                                            else:
                                                value_end += 1
                                        
                                        if value_end < len(answer_text):
                                            value = answer_text[value_start:value_end]
                                            # Обрабатываем экранированные символы
                                            key = key.replace('\\"', '"').replace('\\\\', '\\')
                                            value = value.replace('\\"', '"').replace('\\\\', '\\')
                                            result.append((key, value))
                                            i = value_end + 1
                                            continue
                        i += 1
                    
                    if result:
                        print(f"    ✓ Успешно распарсен через ручной парсинг: {len(result)} сопоставлений")
                        return result
                    
                    # Fallback: простой regex паттерн
                    pattern_simple = r'"([^"]+)":\s*"([^"]+)"'
                    matches = re.findall(pattern_simple, answer_text)
                    if matches:
                        result = [(target, element) for target, element in matches]
                        print(f"    ✓ Успешно распарсен через regex (простой паттерн): {len(result)} сопоставлений")
                        return result
                except Exception as regex_e:
                    print(f"    ⚠ Не удалось распарсить через regex: {regex_e}")
                
                # Пробуем использовать ast.literal_eval как последний fallback
                try:
                    import ast
                    # Находим последнюю закрывающую скобку
                    if last_valid_pos > 0:
                        cleaned_text = answer_text[:last_valid_pos + 1]
                    else:
                        last_brace = answer_text.rfind('}')
                        if last_brace > 0:
                            cleaned_text = answer_text[:last_brace + 1]
                        else:
                            cleaned_text = answer_text
                    
                    parsed = ast.literal_eval(cleaned_text)
                    if isinstance(parsed, dict):
                        result = list(parsed.items())
                        print(f"    ✓ Успешно распарсен через ast.literal_eval: {len(result)} сопоставлений")
                        return result
                except Exception as ast_e:
                    print(f"    ⚠ Не удалось распарсить через ast.literal_eval: {ast_e}")
                
                print(f"    Попробуйте проверить синтаксис JSON")
            except Exception as e:
                print(f"    ⚠ Ошибка при обработке JSON: {e}")
        
        # Обработка JSON, который начинается с {, но не заканчивается на } (лишние символы в конце)
        if answer_text.startswith('{') and not answer_text.endswith('}'):
            try:
                # Находим правильный конец JSON объекта по балансу скобок
                brace_count = 0
                last_valid_pos = -1
                for i, char in enumerate(answer_text):
                    if char == '{':
                        brace_count += 1
                    elif char == '}':
                        brace_count -= 1
                        if brace_count == 0:
                            last_valid_pos = i
                            break
                
                if last_valid_pos > 0:
                    cleaned_text = answer_text[:last_valid_pos + 1]
                    try:
                        mappings_dict = json.loads(cleaned_text)
                        if isinstance(mappings_dict, dict):
                            result = list(mappings_dict.items())
                            print(f"    ✓ Успешно распарсен JSON-объект (после удаления лишних символов): {len(result)} сопоставлений")
                            return result
                    except:
                        # Пробуем ast.literal_eval
                        try:
                            import ast
                            parsed = ast.literal_eval(cleaned_text)
                            if isinstance(parsed, dict):
                                result = list(parsed.items())
                                print(f"    ✓ Успешно распарсен через ast.literal_eval (после очистки): {len(result)} сопоставлений")
                                return result
                        except:
                            pass
            except:
                pass
        
        # Формат 2: Список кортежей
        if answer_text.startswith('[') and answer_text.endswith(']'):
            import ast
            try:
                # Пробуем парсить как Python список кортежей
                parsed = ast.literal_eval(answer_text)
                if isinstance(parsed, list):
                    return parsed
            except:
                pass
        
        # Формат 3: Список пар через разделитель (-> или :)
        # Ищем паттерн "цель -> элемент" или "цель: элемент"
        # НЕ используем этот формат, если текст начинается с { (это был JSON)
        if (not answer_text.startswith('{')) and ('->' in answer_text or ':' in answer_text):
            pairs = []
            # Разделяем по точке с запятой
            parts = re.split(r';\s*', answer_text)
            for part in parts:
                part = part.strip()
                if not part:
                    continue
                
                # Пробуем разделить по -> или :
                if '->' in part:
                    target, element = part.split('->', 1)
                elif ':' in part:
                    # Берем только первое вхождение :, так как в тексте могут быть двоеточия
                    target, element = part.split(':', 1)
                else:
                    continue
                
                target = target.strip().strip('"').strip("'")
                element = element.strip().strip('"').strip("'")
                
                if target and element:
                    pairs.append((target, element))
            
            if pairs:
                return pairs
        
        # Если ничего не подошло, возвращаем пустой список
        print(f"    ⚠ Не удалось распарсить drag and drop ответ: '{answer_text[:100]}...'")
        return []
        
    except Exception as e:
        print(f"    ⚠ Ошибка при парсинге drag and drop ответа: {e}")
        return []

def read_task_data_from_excel(excel_path="test.xlsx"):
    """Читает данные задач из Excel файла
    Возвращает DataFrame с данными
    Поддерживает работу как из обычного скрипта, так и из .exe файла"""
    try:
        # Если запущено из .exe файла (PyInstaller), используем правильный путь
        if getattr(sys, 'frozen', False):
            # Запущено из .exe - файлы распакованы во временную папку
            base_path = sys._MEIPASS
            full_path = os.path.join(base_path, excel_path)
        else:
            # Запущено как обычный скрипт
            full_path = excel_path
        
        # Если файл не найден по указанному пути, пробуем найти в текущей директории
        if not os.path.exists(full_path):
            # Пробуем в текущей директории exe/скрипта
            if getattr(sys, 'frozen', False):
                # Для exe - текущая директория, где находится exe файл
                exe_dir = os.path.dirname(sys.executable)
                full_path = os.path.join(exe_dir, excel_path)
            else:
                # Для скрипта - директория скрипта
                script_dir = os.path.dirname(os.path.abspath(__file__))
                full_path = os.path.join(script_dir, excel_path)
        
        df = pd.read_excel(full_path)
        print(f"  Прочитано строк из Excel: {len(df)}")
        print(f"  Колонки: {list(df.columns)}")
        print(f"  Файл: {full_path}")
        return df
    except FileNotFoundError as e:
        print(f"  ⚠ ОШИБКА: Excel файл не найден!")
        print(f"  Искали файл: {excel_path}")
        print(f"  Пробовали путь: {full_path if 'full_path' in locals() else excel_path}")
        print(f"  Убедитесь, что файл {excel_path} находится в той же папке, что и программа")
        return None
    except Exception as e:
        print(f"  ⚠ Ошибка при чтении Excel файла: {e}")
        print(f"  Пробовали путь: {full_path if 'full_path' in locals() else excel_path}")
        import traceback
        traceback.print_exc()
        return None

def process_randomized_tasks_with_ai(driver, api_key=None, model=None, max_tasks=50):
    """Обрабатывает рандомизированные задачи после контрольного теста с помощью AI
    Продолжает обрабатывать задачи до тех пор, пока они не закончатся или не достигнут max_tasks"""
    try:
        print("\n" + "=" * 50)
        print("Обрабатываем рандомизированные задачи с помощью AI...")
        print("=" * 50)
        
        task_count = 0
        previous_url = None
        consecutive_same_url = 0  # Счетчик для отслеживания зацикливания
        
        while task_count < max_tasks:
            current_url = driver.current_url
            print(f"\n  [AI] Задача {task_count + 1}")
            print(f"  [AI] Текущий URL: {current_url}")
            
            # Проверяем, не зациклились ли мы
            if previous_url and current_url == previous_url:
                consecutive_same_url += 1
                if consecutive_same_url >= 2:
                    print("  [AI] URL не изменился после нескольких попыток - возможно, все задачи завершены")
                    break
            else:
                consecutive_same_url = 0
            
            # Проверяем, находимся ли мы на странице задачи
            if "/trainings/" not in current_url and "/tasks/" not in current_url:
                print("  [AI] Мы не на странице задачи - возможно, все задачи завершены")
                break
            
            # Парсим и обрабатываем задачу с помощью AI
            result = handle_randomized_task_with_ai(driver, api_key, model)
            
            if result == "homework_completed":
                print("  [AI] Все задачи завершены!")
                return "homework_completed"
            elif result:
                task_count += 1
                previous_url = current_url
                
                # Ждем загрузки следующей задачи
                time.sleep(2)
                
                # Проверяем, загрузилась ли следующая задача
                new_url = driver.current_url
                if new_url != current_url:
                    # URL изменился - перешли на новую задачу
                    print(f"  [AI] Перешли на новую задачу: {new_url}")
                    previous_url = new_url
                    consecutive_same_url = 0
                    continue
                else:
                    # URL не изменился - проверяем, есть ли кнопка "Далее"
                    print("  [AI] URL не изменился после обработки")
                    try:
                        # Ждем появления кнопки "Далее" (она может появиться после отправки ответа)
                        wait = WebDriverWait(driver, 3)
                        next_button = wait.until(
                            EC.element_to_be_clickable((By.ID, "training-task-page-make-answer"))
                        )
                        button_text = next_button.text.strip().lower()
                        if "далее" in button_text or "next" in button_text:
                            print("  [AI] Найдена кнопка 'Далее', нажимаем...")
                            next_button.click()
                            time.sleep(2)
                            
                            # Проверяем, изменился ли URL после нажатия
                            final_url = driver.current_url
                            if final_url != new_url:
                                print(f"  [AI] Перешли на новую задачу: {final_url}")
                                previous_url = final_url
                                consecutive_same_url = 0
                                continue
                            else:
                                print("  [AI] URL не изменился после нажатия 'Далее' - возможно, это была последняя задача")
                                break
                    except:
                        print("  [AI] Кнопка 'Далее' не найдена - возможно, все задачи завершены")
                        break
            else:
                print("  [AI] Ошибка при обработке задачи, продолжаем...")
                time.sleep(1)
                # Пробуем перейти к следующей задаче вручную
                try:
                    next_button = driver.find_element(By.ID, "training-task-page-make-answer")
                    button_text = next_button.text.strip().lower()
                    if "далее" in button_text or "next" in button_text:
                        next_button.click()
                        time.sleep(2)
                        continue
                except:
                    print("  [AI] Не удалось найти кнопку перехода - завершаем обработку")
                    break
        
        print(f"\n  [AI] Обработано задач: {task_count}")
        if task_count > 0:
            return True
        else:
            return False
        
    except Exception as e:
        print(f"  ⚠ Ошибка при обработке рандомизированных задач: {e}")
        import traceback
        traceback.print_exc()
        return False

def process_tasks_from_excel(driver, excel_path="test.xlsx"):
    """Обрабатывает все задачи текущего домашнего задания из Excel"""
    try:
        # Извлекаем lesson_id из текущего URL (может быть необязательно для новых форматов)
        current_url = driver.current_url
        print(f"\n  Текущий URL: {current_url}")
        
        lesson_id = None
        match = re.search(r'/lessons/(\d+)/tasks', current_url)
        if match:
            lesson_id = match.group(1)
            print(f"  Найден lesson_id: {lesson_id}")
        else:
            # Для новых форматов (ftest1.xlsx, ftest2.xlsx) lesson_id может быть не нужен
            print("  [DEBUG] lesson_id не найден в URL (возможно, новый формат Excel)")
        
        # Читаем данные из Excel
        print("\n" + "=" * 50)
        print("Читаем данные из Excel...")
        print("=" * 50)
        df = read_task_data_from_excel(excel_path)
        
        if df is None or len(df) == 0:
            print("  ⚠ Нет данных в Excel файле")
            return False
        
        # Находим колонки
        homework_column = None
        answer_column = None
        description_column = None
        
        for col in df.columns:
            col_lower = col.lower()
            if 'homework' in col_lower:
                homework_column = col
            elif 'answer' in col_lower or 'ответ' in col_lower:
                answer_column = col
            elif 'description' in col_lower or 'описание' in col_lower:
                description_column = col
        
        if answer_column is None:
            print("  ⚠ Не найдена колонка 'Answer' в Excel")
            return False
        
        # Для новых форматов (ftest1.xlsx, ftest2.xlsx) колонка Homework может отсутствовать
        # В этом случае используем все строки из Excel
        if homework_column:
            # Старый формат: фильтруем задачи по текущему homework ID
            if lesson_id is None:
                print("  ⚠ Не удалось извлечь lesson_id из URL")
                return False
            
            df[homework_column] = df[homework_column].astype(str)
            homework_tasks = df[df[homework_column] == lesson_id].copy()
            
            if len(homework_tasks) == 0:
                print(f"  ⚠ Не найдено задач для homework ID: {lesson_id}")
                print(f"  Доступные homework ID в Excel: {df[homework_column].unique().tolist()}")
                return False
        else:
            # Новый формат: используем все строки из Excel (для ftest1.xlsx, ftest2.xlsx)
            homework_tasks = df.copy()
            print(f"  [DEBUG] Колонка 'Homework' не найдена, используем все строки из Excel (новый формат)")
        
        print(f"\n  Найдено задач для homework {lesson_id}: {len(homework_tasks)}")
        
        # Обрабатываем задачи по порядку
        task_index = 0
        previous_url = None  # Сохраняем предыдущий URL для проверки зацикливания
        processed_task_ids = set()  # Отслеживаем обработанные ID задач
        
        while task_index < len(homework_tasks):
            task_data = homework_tasks.iloc[task_index]
            
            # Проверяем текущий URL перед обработкой задачи
            current_url = driver.current_url
            
            # Извлекаем ID задачи из URL для более точного сравнения
            # URL может быть: /lessons/6010/tasks/1144363
            current_task_id = None
            previous_task_id = None
            
            match_current = re.search(r'/tasks/(\d+)', current_url)
            if match_current:
                current_task_id = match_current.group(1)
            
            if previous_url:
                match_previous = re.search(r'/tasks/(\d+)', previous_url)
                if match_previous:
                    previous_task_id = match_previous.group(1)
            
            # Отладочная информация
            print(f"\n  [DEBUG] Итерация {task_index + 1}/{len(homework_tasks)}")
            print(f"  [DEBUG] Текущий URL: {current_url}")
            print(f"  [DEBUG] Текущий ID задачи: {current_task_id}")
            print(f"  [DEBUG] Предыдущий URL: {previous_url}")
            print(f"  [DEBUG] Предыдущий ID задачи: {previous_task_id}")
            print(f"  [DEBUG] Обработанные ID задач: {processed_task_ids}")
            
            # Проверяем, не обработали ли мы уже эту задачу
            # Это должно быть ПЕРВОЙ проверкой, чтобы не обрабатывать одну задачу дважды
            # НО: если мы только что перешли на эту задачу (previous_task_id != current_task_id), это нормально
            if current_task_id and current_task_id in processed_task_ids:
                # Проверяем, действительно ли мы застряли на этой задаче
                # Если previous_task_id == current_task_id, значит мы обрабатываем одну и ту же задачу дважды
                if previous_task_id and previous_task_id == current_task_id:
                    # Мы действительно застряли на одной задаче - пропускаем её и переходим к следующей
                    print(f"\n  ⚠ Задача {current_task_id} уже была обработана, пропускаем её и переходим к следующей.")
                    # Просто увеличиваем индекс и продолжаем - не пытаемся перейти дальше
                    previous_url = current_url
                    task_index += 1
                    continue
                else:
                    # Это нормальная ситуация - мы перешли на новую задачу, которая уже была обработана ранее
                    # Продолжаем обработку (не пропускаем задачу)
                    print(f"  [DEBUG] Задача {current_task_id} уже была обработана, но мы перешли на неё с другой задачи - продолжаем")
                    pass
            #     elif current_url == previous_url:
            #         # Если ID задач нет, сравниваем полный URL
            #         print(f"\n  ⚠ ВНИМАНИЕ: URL не изменился после предыдущей задачи!")
            #         print(f"  URL: {current_url}")
            #         print(f"  Предыдущий URL: {previous_url}")
            #         print(f"  Возможно, мы зациклились. Пропускаем эту задачу и переходим к следующей.")
            #         # Обновляем previous_url перед переходом к следующей задаче
            #         previous_url = current_url
            #         task_index += 1
            #         continue
            
            # Для первой задачи устанавливаем previous_url
            if previous_url is None:
                previous_url = current_url
                print(f"  [DEBUG] Установлен previous_url для первой задачи: {previous_url}")
            
            print(f"\n  {'='*50}")
            print(f"  Задача {task_index + 1}/{len(homework_tasks)}")
            print(f"  Текущий URL: {current_url}")
            print(f"  {'='*50}")
            
            # Выводим описание, если есть
            description_col = None
            for col in df.columns:
                if 'description' in col.lower() or 'описание' in col.lower():
                    description_col = col
                    break
            
            if description_col:
                description = str(task_data[description_col]).strip()
                if description and description != 'nan':
                    print(f"  Описание: {description}")
            
            # Определяем тип задачи на странице ПЕРЕД извлечением ответа
            print("\n  Определяем тип задачи на странице...")
            task_type = detect_task_type(driver)
            
            # Только после определения типа задачи извлекаем ответ из Excel
            # Это гарантирует, что мы используем правильный ответ для текущей задачи
            answer_text = str(task_data[answer_column]).strip()
            
            # Отладочная информация: выводим какой ответ используется для текущей задачи
            print(f"\n  [DEBUG] Задача {task_index + 1}/{len(homework_tasks)}")
            print(f"  [DEBUG] task_index = {task_index}")
            print(f"  [DEBUG] Ответ из Excel для этой задачи: '{answer_text[:100]}...' (первые 100 символов)")
            print(f"  [DEBUG] Тип задачи: {task_type}")
            
            # Проверяем ответ из Excel - если это список/массив, это должна быть checkbox задача
            # Это важно, так как некоторые страницы могут иметь и radio и checkbox элементы
            if answer_text and answer_text != 'nan' and (answer_text.strip().startswith('[') or 
                               (',' in answer_text and ('"' in answer_text or "'" in answer_text)) or
                               ';' in answer_text):
                # Ответ выглядит как список - проверяем, есть ли checkbox на странице
                try:
                    task_form = get_task_form(driver)
                    checkboxes = task_form.find_elements(By.CSS_SELECTOR, "input[type='checkbox']")
                    if checkboxes:
                        print("  ⚠ Ответ из Excel - это список, но задача определена как другой тип")
                        print("  Переопределяем тип задачи на CHECKBOX")
                        task_type = "checkbox"
                except:
                    pass
            
            # Обрабатываем решенные задачи
            if task_type == "solved":
                print("  ✓ Задача уже решена, переходим к следующей")
                # Увеличиваем task_index ПЕРЕД переходом, чтобы использовать правильный ответ из Excel для следующей задачи
                task_index += 1
                print(f"  [DEBUG] Увеличен task_index до {task_index} (задача уже решена, переходим к следующей)")
                
                # Проверяем, не вышли ли мы за пределы списка задач
                if task_index >= len(homework_tasks):
                    print(f"  ✓ Все задачи обработаны")
                    return "homework_completed"
                
                # Обновляем task_data для следующей задачи ПЕРЕД переходом
                task_data = homework_tasks.iloc[task_index]
                print(f"  [DEBUG] Обновлен task_data для задачи {task_index + 1}, ответ: '{str(task_data[answer_column])[:100]}...'")
                
                try:
                    wait = WebDriverWait(driver, 2)
                    next_button = wait.until(EC.element_to_be_clickable((
                        By.CSS_SELECTOR,
                        ".styled__ButtonNext-qDZv, a.styled__Root-ebtVmd, a.fox-Anchor.styled__Root-ebtVmd, button[type='submit'], button[class*='Button']"
                    )))
                    print("  Нажимаем 'Дальше'...")
                    url_before_next = driver.current_url
                    driver.execute_script("arguments[0].scrollIntoView({block: 'center'});", next_button)
                    time.sleep(0.2)
                    try:
                        next_button.click()
                    except:
                        driver.execute_script("arguments[0].click();", next_button)
                    print("  ✓ Переход к следующей задаче")
                    time.sleep(1.5)
                    
                    # Проверяем, что URL изменился
                    url_after_next = driver.current_url
                    if url_before_next != url_after_next:
                        print(f"  ✓ Переход подтвержден (URL изменился: {url_before_next} -> {url_after_next})")
                        previous_url = url_after_next
                        # task_index уже увеличен выше
                    else:
                        # URL не изменился - проверяем, что это означает
                        if "/tasks" not in url_after_next:
                            print(f"  ✓ Похоже, мы вернулись на страницу курса - все задачи выполнены")
                            return "homework_completed"
                        else:
                            # URL не изменился, но мы все еще на странице задач - это последняя задача или зацикливание
                            print(f"  ⚠ URL не изменился после нажатия 'Дальше' - возможно, это последняя задача")
                            print(f"  Возвращаемся на страницу курса")
                            # Извлекаем базовый URL курса из текущего URL
                            match = re.search(r'(https://kb\.cifrium\.ru/teacher/courses/\d+)', url_after_next)
                            if match:
                                course_base_url = match.group(1)
                                driver.get(course_base_url)
                            else:
                                # Пробуем извлечь из lesson URL
                                match = re.search(r'(https://kb\.cifrium\.ru/teacher/lessons/\d+)', url_after_next)
                                if match:
                                    lesson_url = match.group(1)
                                    # Удаляем /tasks из URL если есть
                                    if '/tasks' in lesson_url:
                                        lesson_url = lesson_url.replace('/tasks', '')
                                    # Извлекаем course_id из lesson_id
                                    lesson_match = re.search(r'/lessons/(\d+)', lesson_url)
                                    if lesson_match:
                                        # Возвращаемся на страницу курса (нужно знать course_id)
                                        # Пока просто возвращаем homework_completed
                                        return "homework_completed"
                            time.sleep(2)
                            return "homework_completed"
                    continue
                except Exception as e:
                    print(f"  ⚠ Не удалось найти кнопку перехода: {e}")
                    previous_url = driver.current_url
                    task_index += 1
                    continue
            
            if task_type == "unknown":
                print("  ⚠ Не удалось определить тип задачи")
                # Дополнительная проверка: может быть задача уже решена (HTML изменился)
                try:
                    task_form = get_task_form(driver)
                    # Проверяем наличие элементов Solved более тщательно
                    solved_elements = task_form.find_elements(By.XPATH, ".//*[contains(@class, 'Solved') or contains(text(), 'Правильный ответ') or contains(text(), 'Ваш ответ')]")
                    if solved_elements:
                        print("  ✓ Задача уже решена (найдены элементы Solved при дополнительной проверке)")
                        # Пытаемся найти кнопку "Дальше"
                        try:
                            wait = WebDriverWait(driver, 2)
                            next_button = wait.until(EC.element_to_be_clickable((
                                By.CSS_SELECTOR,
                                ".styled__ButtonNext-qDZv, a.styled__Root-ebtVmd, a.fox-Anchor.styled__Root-ebtVmd, button[type='submit'], button[class*='Button']"
                            )))
                            print("  Нажимаем 'Дальше'...")
                            url_before_next = driver.current_url
                            driver.execute_script("arguments[0].scrollIntoView({block: 'center'});", next_button)
                            time.sleep(0.2)
                            try:
                                next_button.click()
                            except:
                                driver.execute_script("arguments[0].click();", next_button)
                            print("  ✓ Переход к следующей задаче")
                            time.sleep(1.5)
                            
                            url_after_next = driver.current_url
                            if url_before_next != url_after_next:
                                print(f"  ✓ Переход подтвержден (URL изменился: {url_before_next} -> {url_after_next})")
                                previous_url = url_after_next
                                task_index += 1
                            else:
                                # URL не изменился - это последняя задача
                                print(f"  ⚠ URL не изменился после нажатия 'Дальше' - возможно, это последняя задача")
                                print(f"  Возвращаемся на страницу курса")
                                match = re.search(r'(https://kb\.cifrium\.ru/teacher/courses/\d+)', url_after_next)
                                if match:
                                    course_base_url = match.group(1)
                                    driver.get(course_base_url)
                                else:
                                    return "homework_completed"
                                time.sleep(2)
                                return "homework_completed"
                            continue
                        except:
                            pass
                except:
                    pass
                
                # Проверяем, может быть задача уже решена и есть кнопка "Дальше"
                try:
                    wait = WebDriverWait(driver, 1)  # Уменьшено время ожидания до 1 секунды
                    next_button = wait.until(EC.element_to_be_clickable((
                        By.CSS_SELECTOR,
                        ".styled__ButtonNext-qDZv, a.styled__Root-ebtVmd, a.fox-Anchor.styled__Root-ebtVmd"
                    )))
                    print("  Задача уже решена, нажимаем 'Дальше'...")
                    url_before_next = driver.current_url
                    driver.execute_script("arguments[0].scrollIntoView({block: 'center'});", next_button)
                    time.sleep(0.2)  # Уменьшено время ожидания после скролла
                    try:
                        next_button.click()
                    except:
                        driver.execute_script("arguments[0].click();", next_button)
                    print("  ✓ Переход к следующей задаче")
                    time.sleep(1)  # Уменьшено время ожидания после перехода
                    
                    # Проверяем, действительно ли мы перешли на новую задачу
                    url_after_next = driver.current_url
                    if url_before_next != url_after_next:
                        print(f"  ✓ Переход подтвержден (URL изменился: {url_before_next} -> {url_after_next})")
                        previous_url = url_after_next
                        task_index += 1
                    else:
                        # URL не изменился - возможно это была последняя задача
                        if "/tasks" not in url_after_next:
                            print(f"  ✓ Похоже, мы вернулись на страницу курса - все задачи выполнены")
                            return "homework_completed"
                        else:
                            # URL не изменился, но мы все еще на странице задач - это последняя задача
                            print(f"  ⚠ URL не изменился после нажатия 'Дальше' - возможно, это последняя задача")
                            print(f"  Возвращаемся на страницу курса")
                            match = re.search(r'(https://kb\.cifrium\.ru/teacher/courses/\d+)', url_after_next)
                            if match:
                                course_base_url = match.group(1)
                                driver.get(course_base_url)
                            else:
                                # Пробуем извлечь из lesson URL
                                match = re.search(r'(https://kb\.cifrium\.ru/teacher/lessons/\d+)', url_after_next)
                                if match:
                                    lesson_url = match.group(1).replace('/tasks', '')
                                    # Возвращаемся на страницу курса
                                    return "homework_completed"
                            time.sleep(2)
                            return "homework_completed"
                    continue
                except:
                    print("  ⚠ Задача не решена и тип не определен, пропускаем")
                    previous_url = driver.current_url  # Обновляем previous_url
                    task_index += 1
                    continue
            
            # Подготавливаем ответ в зависимости от типа задачи
            task_answer = None
            
            # Пропускаем пустые ответы (answer_text уже определен выше)
            if not answer_text or answer_text == 'nan':
                print(f"  ⚠ Пустой ответ в Excel, пропускаем задачу")
                previous_url = driver.current_url  # Обновляем previous_url
                task_index += 1
                continue
            
            print(f"\n  Ответ из Excel: '{answer_text[:100]}...' (первые 100 символов)")
            
            # Обрабатываем ответ в зависимости от типа задачи
            if task_type == "checkbox":
                # Для checkbox ответ в формате массива строк в кавычках или через разделитель
                print("  Обрабатываем checkbox задачу...")
                task_form = get_task_form(driver)
                checkboxes = task_form.find_elements(By.CSS_SELECTOR, "input[type='checkbox']")
                
                # Парсим ответ (поддерживаем оба формата)
                # Сначала проверяем, является ли это JSON-массивом (начинается с [)
                if answer_text.strip().startswith('[') and answer_text.strip().endswith(']'):
                    # Формат JSON-массива с кавычками
                    answer_parts = parse_checkbox_answer(answer_text)
                elif ';' in answer_text:
                    # Простой формат с разделителем ;
                    answer_parts = re.split(r';\s*', answer_text)
                    answer_parts = [part.strip().strip('"').strip("'") for part in answer_parts if part.strip()]
                elif ',' in answer_text and not (answer_text.strip().startswith('[') or '"' in answer_text or "'" in answer_text):
                    # Простой формат с разделителем , (только если это не JSON и нет кавычек)
                    answer_parts = re.split(r',\s*', answer_text)
                    answer_parts = [part.strip().strip('"').strip("'") for part in answer_parts if part.strip()]
                else:
                    # Формат с кавычками (используем parse_checkbox_answer)
                    answer_parts = parse_checkbox_answer(answer_text)
                
                print(f"    Распарсенные варианты ответа: {answer_parts}")
                
                # Используем строгое сопоставление для поиска чекбоксов
                selected_values = find_checkbox_matches(answer_parts, checkboxes)
                
                if selected_values:
                    task_answer = selected_values
                    print(f"    Всего выбрано чекбоксов: {len(selected_values)}")
                else:
                    print("  ⚠ Не найдены чекбоксы с соответствующим текстом")
                    previous_url = driver.current_url  # Обновляем previous_url
                    task_index += 1
                    continue
            
            elif task_type == "radio":
                # Для radio нужно найти радио-кнопку по тексту ответа
                print("  Обрабатываем radio задачу...")
                task_form = get_task_form(driver)
                radios = task_form.find_elements(By.CSS_SELECTOR, "input[type='radio']")
                
                # Используем строгое сопоставление для поиска наиболее подходящего варианта
                found_radio, found_value = find_best_radio_match(answer_text, radios)
                
                if found_radio and found_value:
                    # Получаем текст для вывода
                    try:
                        # Пробуем получить текст из правильного места
                        try:
                            label_div = found_radio.find_element(By.XPATH, "./following-sibling::div[contains(@class, 'styled__Label') or contains(@class, 'MathContent_root')]")
                            try:
                                span = label_div.find_element(By.XPATH, ".//span[contains(@class, 'MathContent_content')]")
                                label_text = span.text.strip()
                            except:
                                label_text = label_div.text.strip()
                        except:
                            parent = found_radio.find_element(By.XPATH, "./..")
                            label_text = parent.text.strip()
                        print(f"    ✓ Найдена радио-кнопка: '{label_text[:100]}...' (value: {found_value})")
                    except:
                        print(f"    ✓ Найдена радио-кнопка (value: {found_value})")
                    task_answer = found_value
                    print(f"    [DEBUG] task_answer установлен в: {task_answer} (тип: {type(task_answer)})")
                else:
                    print(f"  ⚠ Не найдена радио-кнопка с соответствующим текстом для: '{answer_text[:50]}...'")
                    # Выводим доступные варианты для отладки
                    try:
                        print("    Доступные варианты:")
                        for radio in radios[:5]:  # Показываем первые 5
                            try:
                                value = radio.get_attribute("value")
                                # Пробуем получить текст из правильного места
                                label_text = None
                                try:
                                    label_div = radio.find_element(By.XPATH, "./following-sibling::div[contains(@class, 'styled__Label') or contains(@class, 'MathContent_root')]")
                                    try:
                                        # Сначала пробуем найти span с точным классом MathContent_content__2a8XE
                                        span = label_div.find_element(By.CSS_SELECTOR, "span.MathContent_content__2a8XE")
                                        label_text = span.text.strip()
                                    except:
                                        try:
                                            span = label_div.find_element(By.XPATH, ".//span[contains(@class, 'MathContent_content')]")
                                            label_text = span.text.strip()
                                        except:
                                            label_text = label_div.text.strip()
                                except:
                                    try:
                                        parent = radio.find_element(By.XPATH, "./..")
                                        label_text = parent.text.strip()
                                    except:
                                        pass
                                
                                if label_text:
                                    print(f"      - value={value}: '{label_text[:80]}...' (длина: {len(label_text)})")
                                else:
                                    print(f"      - value={value}: [не удалось извлечь текст]")
                            except Exception as e:
                                print(f"      - [ошибка при извлечении текста: {e}]")
                    except:
                        pass
                    
                    # ВАЖНО: Если не найдено совпадение, не пропускаем задачу, а пытаемся выбрать первый вариант
                    # или останавливаемся с ошибкой, чтобы пользователь мог исправить Excel
                    print(f"  ⚠ ОШИБКА: Не удалось найти совпадение для ответа из Excel")
                    print(f"  ⚠ Ответ в Excel может быть неправильным или неполным")
                    print(f"  ⚠ Пропускаем эту задачу и переходим к следующей")
                    
                    # Обновляем previous_url и увеличиваем индекс, чтобы избежать зацикливания
                    previous_url = driver.current_url
                    
                    # НЕ добавляем задачу в processed_task_ids здесь - она будет добавлена после успешной обработки
                    # Это предотвращает ложные срабатывания проверки зацикливания
                    
                    # Проверяем, не зациклились ли мы на той же задаче
                    if current_task_id and current_task_id in processed_task_ids:
                        print(f"  ⚠ Обнаружено зацикливание на задаче {current_task_id}")
                        print(f"  ⚠ Пытаемся перейти к следующей задаче вручную...")
                        # Пробуем найти кнопку "Дальше" и перейти
                        try:
                            next_button = WebDriverWait(driver, 3).until(
                                EC.element_to_be_clickable((By.XPATH, "//a[contains(@class, 'styled__ButtonNext')] | //button[contains(text(), 'Дальше')] | //a[contains(text(), 'Дальше')]"))
                            )
                            next_button.click()
                            time.sleep(2)
                            print(f"  ✓ Перешли к следующей задаче вручную")
                            # Обновляем previous_url после перехода
                            previous_url = driver.current_url
                        except:
                            print(f"  ⚠ Не удалось перейти к следующей задаче, пропускаем")
                    
                    task_index += 1
                    continue
            
            elif task_type == "drag_and_drop":
                print("  Обрабатываем drag and drop задачу...")
                # Парсим ответ для drag and drop
                mappings = parse_drag_and_drop_answer(answer_text)
                
                if mappings:
                    print(f"    Распарсено сопоставлений: {len(mappings)}")
                    for target, element in mappings:
                        print(f"      - '{target[:50]}...' -> '{element}'")
                    task_answer = mappings
                else:
                    # Если ответ не парсится как drag_and_drop и это просто число или короткая строка,
                    # возможно это на самом деле text задача
                    answer_clean = answer_text.strip()
                    if (answer_clean.isdigit() or 
                        (len(answer_clean) < 50 and not answer_clean.startswith('{') and not answer_clean.startswith('['))):
                        print("  Ответ похож на text (число или короткая строка), пробуем обработать как text...")
                        task_answer = answer_text
                        # Не меняем task_type, просто используем answer_text как есть
                    else:
                        print("  ⚠ Не удалось распарсить drag and drop ответ")
                        print("  Форматы: JSON {'цель': 'элемент'}, список пар 'цель -> элемент; ...', или [('цель', 'элемент'), ...]")
                        previous_url = driver.current_url  # Обновляем previous_url
                        task_index += 1
                        continue
            
            elif task_type == "code":
                print("  Обрабатываем code задачу...")
                task_answer = answer_text
            
            elif task_type == "text":
                print("  Обрабатываем text задачу...")
                print(f"  [DEBUG] Используем ответ для text задачи: '{answer_text[:100]}...' (первые 100 символов)")
                print(f"  [DEBUG] task_index = {task_index}, task_data[answer_column] = '{str(task_data[answer_column])[:100]}...'")
                task_answer = answer_text
            
            # Обрабатываем задачу
            if task_answer is not None:
                print(f"\n  Обрабатываем задачу...")
                
                # Сохраняем текущий URL перед обработкой задачи
                url_before = driver.current_url
                
                result = handle_task(driver, task_answer)
                
                if result == "homework_completed":
                    print(f"  ✓ Домашнее задание {lesson_id} полностью завершено!")
                    print("  Возвращаемся на страницу курса для продолжения с другими заданиями")
                    return "homework_completed"
                elif result:
                    print(f"  ✓ Задача {task_index + 1} обработана успешно")
                    
                    # Увеличиваем task_index сразу после успешной обработки задачи
                    # Это гарантирует, что следующая итерация будет использовать правильный ответ из Excel
                    task_index += 1
                    print(f"  [DEBUG] Увеличен task_index до {task_index} после успешной обработки задачи")
                    
                    # Проверяем, действительно ли мы перешли на новую задачу
                    time.sleep(2)  # Ждем загрузки следующей страницы
                    url_after = driver.current_url
                    
                    # Извлекаем ID задач из URL для сравнения
                    task_id_before = None
                    task_id_after = None
                    
                    match_before = re.search(r'/tasks/(\d+)', url_before)
                    if match_before:
                        task_id_before = match_before.group(1)
                    
                    match_after = re.search(r'/tasks/(\d+)', url_after)
                    if match_after:
                        task_id_after = match_after.group(1)
                    
                    # Если URL изменился И ID задачи изменился, значит мы перешли на новую задачу
                    if url_before != url_after:
                        if task_id_before and task_id_after and task_id_before != task_id_after:
                            # ID задачи изменился - мы действительно на новой задаче
                            print(f"  ✓ Переход на новую задачу подтвержден (ID задачи изменился)")
                            print(f"  [DEBUG] ID задачи до: {task_id_before}")
                            print(f"  [DEBUG] ID задачи после: {task_id_after}")
                            print(f"  [DEBUG] URL до: {url_before}")
                            print(f"  [DEBUG] URL после: {url_after}")
                            # Добавляем предыдущую задачу в список обработанных
                            processed_task_ids.add(task_id_before)
                            previous_url = url_after  # Обновляем previous_url
                            print(f"  [DEBUG] Обновлен previous_url: {previous_url}")
                            # task_index уже увеличен выше после успешной обработки задачи
                            print(f"  [DEBUG] task_index уже увеличен до: {task_index}")
                        elif not task_id_before and task_id_after:
                            # Перешли с главной страницы на страницу задачи - это нормально
                            # Это означает, что мы обработали первую задачу из списка и перешли на её страницу
                            print(f"  ✓ Переход на страницу задачи подтвержден")
                            print(f"  [DEBUG] URL до: {url_before}")
                            print(f"  [DEBUG] URL после: {url_after}")
                            print(f"  [DEBUG] ID задачи: {task_id_after}")
                            # НЕ добавляем задачу в processed_task_ids здесь - она будет добавлена после обработки
                            previous_url = url_after  # Обновляем previous_url
                            print(f"  [DEBUG] Обновлен previous_url: {previous_url}")
                            # НЕ увеличиваем task_index - мы еще не обработали эту задачу, только перешли на неё
                            print(f"  [DEBUG] Продолжаем обработку задачи {task_id_after}")
                        else:
                            # URL изменился, но ID задачи тот же - странно, но продолжаем
                            print(f"  ⚠ URL изменился, но ID задачи остался тем же")
                            print(f"  [DEBUG] URL до: {url_before}")
                            print(f"  [DEBUG] URL после: {url_after}")
                            print(f"  [DEBUG] ID задачи: {task_id_after}")
                            previous_url = url_after  # Обновляем previous_url
                            # Не увеличиваем task_index - возможно, это была ошибка
                    else:
                        # URL не изменился - возможно это была последняя задача или произошла ошибка
                        print(f"  ⚠ URL не изменился после обработки задачи")
                        print(f"  URL до: {url_before}")
                        print(f"  URL после: {url_after}")
                        
                        # Проверяем, может быть это последняя задача и мы вернулись на страницу курса
                        if "/tasks" not in url_after:
                            print(f"  ✓ Похоже, мы вернулись на страницу курса - все задачи выполнены")
                            return "homework_completed"
                        else:
                            # Мы все еще на странице задач - увеличиваем индекс, чтобы не зациклиться
                            print(f"  ⚠ Все еще на странице задач, увеличиваем индекс чтобы избежать зацикливания")
                            previous_url = url_after  # Обновляем previous_url
                            task_index += 1
                else:
                    print(f"  ⚠ Ошибка при обработке задачи {task_index + 1}")
                    previous_url = driver.current_url  # Обновляем previous_url
                    task_index += 1
                    # Продолжаем со следующей задачей
            else:
                print("  ⚠ Не удалось подготовить ответ для задачи")
                previous_url = driver.current_url  # Обновляем previous_url
                task_index += 1
                continue
        
        print(f"\n  ✓ Все задачи для homework {lesson_id} обработаны!")
        return True
            
    except Exception as e:
        print(f"  ⚠ Ошибка при обработке задач из Excel: {e}")
        import traceback
        traceback.print_exc()
        return False

def handle_kinescope_video(driver):
    """Находит Kinescope iframe с id, начинающимся с __kinescope_player (число в конце может варьироваться), 
    запускает видео и перематывает на конец
    Возвращает: True если видео найдено и обработано, False если видео не найдено, None если ошибка"""
    try:
        wait = WebDriverWait(driver, 15)  # Увеличил время ожидания
        
        print("  Ищем Kinescope iframe...")
        
        # Пробуем несколько способов поиска iframe
        iframe = None
        
        # Способ 1: Поиск по частичному совпадению id, начинающемуся с __kinescope_player
        try:
            print("  Пробуем найти iframe по ID, начинающемуся с '__kinescope_player'...")
            iframe = wait.until(EC.presence_of_element_located((
                By.XPATH, 
                "//iframe[starts-with(@id, '__kinescope_player')]"
            )))
            print("  ✓ Kinescope iframe найден по частичному совпадению ID")
        except Exception as e1:
            print(f"  Не найден по частичному совпадению ID: {e1}")
            
            # Способ 2: Поиск по частичному совпадению id (содержит kinescope)
            try:
                print("  Пробуем найти iframe по частичному совпадению id (содержит 'kinescope')...")
                iframe = wait.until(EC.presence_of_element_located((
                    By.XPATH, 
                    "//iframe[contains(@id, 'kinescope')]"
                )))
                print("  ✓ Kinescope iframe найден по частичному совпадению")
            except Exception as e2:
                print(f"  Не найден по частичному совпадению: {e2}")
                
                # Способ 3: Поиск по src, содержащему kinescope
                try:
                    print("  Пробуем найти iframe по src (kinescope.io)...")
                    iframe = wait.until(EC.presence_of_element_located((
                        By.XPATH, 
                        "//iframe[contains(@src, 'kinescope')]"
                    )))
                    print("  ✓ Kinescope iframe найден по src")
                except Exception as e3:
                    print(f"  Не найден по src: {e3}")
                    
                    # Способ 4: Поиск всех iframe и проверка
                    try:
                        print("  Пробуем найти среди всех iframe...")
                        all_iframes = driver.find_elements(By.TAG_NAME, "iframe")
                        print(f"  Найдено iframe на странице: {len(all_iframes)}")
                        for i, ifr in enumerate(all_iframes):
                            ifr_id = ifr.get_attribute("id") or ""
                            ifr_src = ifr.get_attribute("src") or ""
                            print(f"    Iframe {i+1}: id='{ifr_id}', src содержит 'kinescope': {'kinescope' in ifr_src.lower()}")
                            if "__kinescope_player" in ifr_id or "kinescope" in ifr_id.lower() or "kinescope" in ifr_src.lower():
                                iframe = ifr
                                print(f"  ✓ Kinescope iframe найден среди всех iframe (индекс {i+1})")
                                break
                    except Exception as e4:
                        print(f"  Ошибка при поиске среди всех iframe: {e4}")
        
        if not iframe:
            print("  ⚠ Kinescope iframe не найден (видео отсутствует на этой странице)")
            return False  # False означает, что видео не найдено
        
        # Получаем информацию об iframe для отладки
        iframe_id = iframe.get_attribute("id") or "нет id"
        iframe_src = iframe.get_attribute("src") or "нет src"
        print(f"  Найденный iframe: id='{iframe_id}', src начинается с: {iframe_src[:50] if len(iframe_src) > 50 else iframe_src}...")
        
        # Выполняем клик на странице, чтобы разблокировать автовоспроизведение
        print("  Выполняем клик на странице для разблокировки автовоспроизведения...")
        try:
            # Прокручиваем к iframe
            driver.execute_script("arguments[0].scrollIntoView({block: 'center'});", iframe)
            time.sleep(0.5)
            
            # Кликаем на iframe или на страницу
            try:
                iframe.click()
            except:
                # Если клик на iframe не работает, кликаем на body
                driver.execute_script("document.body.click();")
            
            time.sleep(0.5)
            print("  ✓ Клик выполнен")
        except Exception as click_error:
            print(f"  ⚠ Ошибка при клике: {click_error}, продолжаем...")
        
        # Используем Kinescope Iframe API для управления видео
        print("  Загружаем Kinescope Iframe API...")
        result = None
        try:
            result = driver.execute_script("""
            const iframeElement = arguments[0];
            return new Promise(async (resolve) => {
                try {
                    // Проверяем, что iframe существует
                    if (!iframeElement) {
                        resolve({success: false, error: 'Iframe element is null'});
                        return;
                    }
                    
                    // Загружаем Kinescope Iframe API
                    const script = document.createElement('script');
                    script.src = 'https://unpkg.com/@kinescope/player-iframe-api-loader@latest/dist/index.umd.js';
                    
                    script.onload = async function() {
                        try {
                            // Используем переданный iframe элемент
                            const iframe = iframeElement;
                            if (!iframe) {
                                resolve({success: false, error: 'Kinescope iframe not found'});
                                return;
                            }
                            
                            // Получаем API loader (может быть в разных местах в зависимости от версии)
                            const iframeApiLoader = window.KinescopeIframeApiLoader || 
                                                   window['@kinescope/player-iframe-api-loader'] ||
                                                   (window.kinescope && window.kinescope.IframeApiLoader);
                            
                            if (!iframeApiLoader) {
                                // Пробуем альтернативный способ - прямой доступ к API
                                resolve({success: false, error: 'API loader not found, trying alternative method'});
                                return;
                            }
                            
                            // Создаем player instance
                            const factory = await iframeApiLoader.load();
                            const player = await factory.create(iframe);
                            
                            // Пробуем запустить видео с обработкой ошибок
                            try {
                                await player.play();
                                console.log('Video started');
                            } catch (playError) {
                                console.log('Play error:', playError);
                                // Если ошибка автовоспроизведения, пробуем кликнуть на iframe
                                const errorMsg = playError.message || '';
                                if (playError.name === 'NotAllowedError' || errorMsg.includes('user didn') || errorMsg.includes('interact')) {
                                    console.log('Trying to click on iframe to enable playback...');
                                    // Пробуем кликнуть на iframe через событие
                                    iframe.click();
                                    await new Promise(resolve => setTimeout(resolve, 500));
                                    // Пробуем снова
                                    try {
                                        await player.play();
                                        console.log('Video started after click');
                                    } catch (retryError) {
                                        console.log('Retry play error:', retryError);
                                        // Пробуем использовать setCurrentTime для "активации" плеера
                                        try {
                                            await player.seek(0);
                                            await new Promise(resolve => setTimeout(resolve, 500));
                                            await player.play();
                                            console.log('Video started after seek');
                                        } catch (finalError) {
                                            resolve({success: false, error: 'Could not play video: ' + finalError.toString()});
                                            return;
                                        }
                                    }
                                } else {
                                    throw playError;
                                }
                            }
                            
                            // Ждем немного для загрузки метаданных
                            await new Promise(resolve => setTimeout(resolve, 3000));
                            
                            // Получаем длительность
                            let duration = 0;
                            try {
                                duration = await player.getDuration();
                                console.log('Video duration:', duration);
                            } catch (durError) {
                                console.log('Error getting duration:', durError);
                                // Пробуем еще раз через небольшую задержку
                                await new Promise(resolve => setTimeout(resolve, 1000));
                                try {
                                    duration = await player.getDuration();
                                    console.log('Video duration (retry):', duration);
                                } catch (durError2) {
                                    resolve({success: false, error: 'Could not get video duration: ' + durError2.toString()});
                                    return;
                                }
                            }
                            
                            if (duration && duration > 0) {
                                // Перематываем на 98%
                                const seekTime = duration * 0.997;
                                console.log('Attempting to seek to:', seekTime);
                                
                                try {
                                    await player.seek(seekTime);
                                    console.log('Video seeked to:', seekTime);
                                    
                                    // Ждем, пока видео дойдет до конца и остановится
                                    console.log('Waiting for video to finish...');
                                    let videoEnded = false;
                                    let checkCount = 0;
                                    const maxChecks = 60; // Максимум 60 проверок (около 60 секунд)
                                    
                                    while (!videoEnded && checkCount < maxChecks) {
                                        await new Promise(resolve => setTimeout(resolve, 1000));
                                        
                                        try {
                                            const currentTime = await player.getCurrentTime();
                                            const isPaused = await player.isPaused();
                                            
                                            // Видео закончилось, если currentTime близко к duration или видео на паузе в конце
                                            if (currentTime >= duration - 0.5 || (isPaused && currentTime >= duration * 0.95)) {
                                                videoEnded = true;
                                                console.log('Video ended at:', currentTime);
                                            } else {
                                                checkCount++;
                                                if (checkCount % 5 === 0) {
                                                    console.log(`Waiting... current time: ${currentTime.toFixed(2)}/${duration.toFixed(2)}`);
                                                }
                                            }
                                        } catch (checkError) {
                                            console.log('Error checking video status:', checkError);
                                            checkCount++;
                                            // Если не можем проверить статус, ждем еще немного и считаем, что закончилось
                                            if (checkCount >= 10) {
                                                videoEnded = true;
                                                console.log('Assuming video ended after timeout');
                                            }
                                        }
                                    }
                                    
                                    if (videoEnded) {
                                        console.log('Video finished playing');
                                    } else {
                                        console.log('Timeout waiting for video to finish, continuing...');
                                    }
                                    
                                    resolve({success: true, duration: duration, seekTime: seekTime, videoEnded: videoEnded});
                                } catch (seekError) {
                                    console.log('Seek error:', seekError);
                                    resolve({success: false, error: 'Could not seek video: ' + seekError.toString()});
                                    return;
                                }
                            } else {
                                resolve({success: false, error: 'Could not get video duration or duration is 0'});
                            }
                        } catch (error) {
                            resolve({success: false, error: error.toString()});
                        }
                    };
                    
                    script.onerror = function() {
                        resolve({success: false, error: 'Failed to load API script'});
                    };
                    
                    document.head.appendChild(script);
                } catch (error) {
                    resolve({success: false, error: error.toString()});
                }
            });
        """, iframe)  # Передаем iframe элемент как аргумент
        except Exception as js_error:
            # Если произошла JavaScript ошибка, но iframe был найден, пробуем альтернативный метод
            print(f"  ⚠ JavaScript ошибка при загрузке API: {js_error}")
            print("  Пробуем альтернативный способ...")
            result = None  # Устанавливаем result в None, чтобы перейти к альтернативному методу
        
        if result and result.get('success'):
            duration = result.get('duration', 0)
            seek_time = result.get('seekTime', 0)
            print(f"  ✓ Видео запущено и перемотано на {seek_time:.2f} сек (99% из {duration:.2f} сек)")
            return True
        else:
            error_msg = result.get('error', 'Unknown error') if result else 'No result'
            print(f"  ⚠ API метод не сработал: {error_msg}")
            
            # Пробуем альтернативный способ - работа напрямую с iframe
            print("  Пробуем альтернативный способ через прямой доступ к iframe...")
            try:
                # Переключаемся в iframe
                driver.switch_to.frame(iframe)
                
                # Ищем video элемент
                try:
                    video = wait.until(EC.presence_of_element_located((By.TAG_NAME, "video")))
                    print("  Найдено video в iframe")
                    
                    # Пробуем запустить видео с обработкой ошибок автовоспроизведения
                    try:
                        # Сначала кликаем на video элемент для "разблокировки"
                        driver.execute_script("arguments[0].click();", video)
                        time.sleep(0.3)
                        
                        # Запускаем видео
                        play_result = driver.execute_script("""
                            const video = arguments[0];
                            return video.play().then(() => {
                                return {success: true};
                            }).catch(error => {
                                return {success: false, error: error.toString()};
                            });
                        """, video)
                        
                        if play_result and play_result.get('success'):
                            print("  Видео запущено")
                        else:
                            error_msg = play_result.get('error', 'Unknown error') if play_result else 'No result'
                            print(f"  ⚠ Ошибка при запуске: {error_msg}")
                            # Пробуем еще раз после небольшой задержки
                            time.sleep(0.5)
                            driver.execute_script("arguments[0].play().catch(() => {});", video)
                            print("  Повторная попытка запуска видео")
                    except Exception as play_error:
                        print(f"  ⚠ Ошибка при запуске видео: {play_error}, продолжаем...")
                    
                    time.sleep(3)  # Ждем загрузки метаданных
                    
                    # Получаем длительность
                    duration = 0
                    try:
                        duration = driver.execute_script("return arguments[0].duration;", video)
                        print(f"  Длительность видео: {duration} сек")
                    except Exception as dur_error:
                        print(f"  ⚠ Ошибка при получении длительности: {dur_error}")
                        # Пробуем еще раз
                        time.sleep(1)
                        try:
                            duration = driver.execute_script("return arguments[0].duration;", video)
                            print(f"  Длительность видео (повторная попытка): {duration} сек")
                        except:
                            print("  Не удалось получить длительность видео")
                            driver.switch_to.default_content()
                            return False
                    
                    if duration and duration > 0:
                        # Перематываем на 98%
                        target_time = duration * 0.98
                        print(f"  Перематываем видео на {target_time:.2f} сек (98% из {duration:.2f} сек)...")
                        
                        try:
                            driver.execute_script("arguments[0].currentTime = arguments[1];", video, target_time)
                            
                            # Ждем, пока видео дойдет до конца и остановится
                            print("  Ждем окончания видео...")
                            video_ended = False
                            check_count = 0
                            max_checks = 60  # Максимум 60 проверок (около 60 секунд)
                            
                            while not video_ended and check_count < max_checks:
                                time.sleep(1)
                                
                                try:
                                    current_time = driver.execute_script("return arguments[0].currentTime;", video)
                                    paused = driver.execute_script("return arguments[0].paused;", video)
                                    
                                    # Видео закончилось, если currentTime близко к duration или видео на паузе в конце
                                    if current_time >= duration - 0.5 or (paused and current_time >= duration * 0.95):
                                        video_ended = True
                                        print(f"  Видео закончилось на позиции {current_time:.2f} сек")
                                    else:
                                        check_count += 1
                                        if check_count % 5 == 0:
                                            print(f"  Ожидание... текущая позиция: {current_time:.2f}/{duration:.2f} сек")
                                except Exception as check_error:
                                    print(f"  ⚠ Ошибка при проверке статуса: {check_error}")
                                    check_count += 1
                                    if check_count >= 10:
                                        video_ended = True
                                        print("  Предполагаем, что видео закончилось после таймаута")
                            
                            if video_ended:
                                print("  ✓ Видео закончилось")
                            else:
                                print("  ⚠ Таймаут ожидания окончания видео, продолжаем...")
                            
                            print(f"  ✓ Видео перемотано на {target_time:.2f} сек (98% из {duration:.2f} сек)")
                            
                            driver.switch_to.default_content()
                            return True
                        except Exception as seek_error:
                            print(f"  ⚠ Ошибка при перемотке: {seek_error}")
                            driver.switch_to.default_content()
                            return False
                    else:
                        print("  Не удалось получить длительность видео")
                        driver.switch_to.default_content()
                        return False
                        
                except Exception as video_error:
                    print(f"  Не удалось найти video элемент: {video_error}")
                    driver.switch_to.default_content()
                    return False
                    
            except Exception as iframe_error:
                print(f"  Ошибка при работе с iframe: {iframe_error}")
                try:
                    driver.switch_to.default_content()
                except:
                    pass
                return False
        
    except Exception as e:
        print(f"  ⚠ Ошибка при обработке Kinescope видео: {e}")
        import traceback
        traceback.print_exc()
        try:
            driver.switch_to.default_content()
        except:
            pass
        return False

def main():
    print("=" * 50)
    print("Запуск скрипта...")
    print("=" * 50)
    print()
    
    # Выбор модуля для выполнения
    print("\n" + "=" * 50)
    print("ВЫБОР МОДУЛЯ")
    print("=" * 50)
    print("Выберите модуль для выполнения:")
    print("  1 - Модуль 1 (курс 770, файл test1.xlsx)")
    print("  2 - Модуль 2 (курс 771, файл test.xlsx)")
    print("  3 - Модуль 3 (курс 772, файл test2.xlsx)")
    print("=" * 50)
    
    while True:
        try:
            choice = input("\n>>> Введите номер модуля (1, 2 или 3): ").strip()
            if choice == "1":
                selected_module = 1
                initial_course_url = MAIN_PAGE_URL_1
                initial_course_id = "770"
                initial_excel_file = "test1.xlsx"
                print(f"\n✓ Выбран модуль 1 (курс 770)")
                break
            elif choice == "2":
                selected_module = 2
                initial_course_url = MAIN_PAGE_URL
                initial_course_id = "771"
                initial_excel_file = "test.xlsx"
                print(f"\n✓ Выбран модуль 2 (курс 771)")
                break
            elif choice == "3":
                selected_module = 3
                initial_course_url = MAIN_PAGE_URL_2
                initial_course_id = "772"
                initial_excel_file = "test2.xlsx"
                print(f"\n✓ Выбран модуль 3 (курс 772)")
                break
            else:
                print("  ⚠ Неверный выбор! Введите 1, 2 или 3")
        except KeyboardInterrupt:
            print("\n\nПрервано пользователем")
            return
        except Exception as e:
            print(f"  ⚠ Ошибка: {e}")
    
    driver = None
    try:
        driver = setup_driver()
        print("✓ Браузер создан успешно")
    except Exception as e:
        print(f"\nКРИТИЧЕСКАЯ ОШИБКА: Не удалось запустить браузер")
        print(f"Детали: {e}")
        import traceback
        traceback.print_exc()
        return
    
    if driver is None:
        print("ОШИБКА: driver is None!")
        return
    
    # Открываем главную страницу выбранного модуля
    print(f"\nОткрываем главную страницу модуля {selected_module}: {initial_course_url}")
    driver.get(initial_course_url)
    time.sleep(3)
    
    # Проверяем, нужен ли вход
    current_url = driver.current_url
    print(f"Текущий URL: {current_url}")
    
    # Проверяем, залогинены ли мы
    # Если нас перенаправило на главную страницу (https://kb.cifrium.ru/), значит не залогинены
    needs_login = False
    if current_url == HOME_URL or current_url == HOME_URL.rstrip('/'):
        print("⚠ Обнаружено: не залогинены (перенаправление на главную страницу)")
        needs_login = True
    elif "login" in current_url.lower() or "user/login" in current_url.lower():
        print("⚠ Обнаружена страница входа")
        needs_login = True
    elif MAIN_PAGE_URL_1 in current_url or MAIN_PAGE_URL in current_url or MAIN_PAGE_URL_2 in current_url or "teacher/courses" in current_url:
        print("✓ Уже залогинены! Перешли на целевую страницу.")
        needs_login = False
    else:
        print(f"⚠ Неизвестный URL: {current_url}")
        needs_login = True  # На всякий случай предполагаем, что нужен вход
    
    # Если нужен вход, ждем ручного входа
    if needs_login:
        print("\n" + "=" * 50)
        print("ТРЕБУЕТСЯ ВХОД В СИСТЕМУ")
        print("=" * 50)
        print("Браузер открыт. Пожалуйста, войдите в систему вручную.")
        print("После успешного входа:")
        print(f"1. Убедитесь, что вы на странице: {initial_course_url}")
        print("2. Нажмите Enter в этом окне")
        print("=" * 50)
        input("\n>>> Нажмите Enter после того, как войдете в систему...")
        
        # Проверяем, залогинились ли
        current_url = driver.current_url
        print(f"\nТекущий URL после входа: {current_url}")
        
        if MAIN_PAGE_URL_1 in current_url or MAIN_PAGE_URL in current_url or MAIN_PAGE_URL_2 in current_url or "teacher/courses" in current_url:
            print("✓ Отлично! Вы залогинены и на нужной странице.")
        else:
            print(f"⚠ Текущий URL: {current_url}")
            print("Переходим на целевую страницу...")
            driver.get(initial_course_url)
            time.sleep(3)
            
            final_url = driver.current_url
            if MAIN_PAGE_URL_1 in final_url or MAIN_PAGE_URL in final_url or MAIN_PAGE_URL_2 in final_url or "teacher/courses" in final_url:
                print("✓ Перешли на целевую страницу!")
            else:
                print(f"⚠ Не удалось перейти. Текущий URL: {final_url}")
                print("Попробуйте перейти вручную и нажмите Enter снова...")
                input(">>> Нажмите Enter когда будете на нужной странице...")
    else:
        print("✓ Вы уже залогинены!")
    
    # Финальная проверка
    final_url = driver.current_url
    print(f"\n{'='*50}")
    print(f"ФИНАЛЬНЫЙ URL: {final_url}")
    if MAIN_PAGE_URL_1 in final_url or MAIN_PAGE_URL in final_url or MAIN_PAGE_URL_2 in final_url or "teacher/courses" in final_url:
        print("✓ Сайт открыт и вы залогинены!")
    else:
        print(f"⚠ Текущий URL: {final_url}")
    print(f"{'='*50}\n")
    
    # Продолжаем работу со скриптом
    interrupted = False
    
    # Определяем текущий курс и соответствующий Excel файл на основе выбранного модуля
    current_course_url = initial_course_url
    current_course_id = initial_course_id
    current_excel_file = initial_excel_file
    
    # Проверяем наличие Excel файлов перед началом работы
    print("\n" + "=" * 50)
    print("Проверка наличия Excel файлов...")
    print("=" * 50)
    
    # Функция для проверки файла
    def check_excel_file(filename):
        if getattr(sys, 'frozen', False):
            # Для exe - проверяем в директории exe
            exe_dir = os.path.dirname(sys.executable)
            file_path = os.path.join(exe_dir, filename)
            if os.path.exists(file_path):
                return file_path
            # Также проверяем во временной папке PyInstaller
            try:
                base_path = sys._MEIPASS
                file_path = os.path.join(base_path, filename)
                if os.path.exists(file_path):
                    return file_path
            except:
                pass
        else:
            # Для скрипта - проверяем в директории скрипта
            script_dir = os.path.dirname(os.path.abspath(__file__))
            file_path = os.path.join(script_dir, filename)
            if os.path.exists(file_path):
                return file_path
        
        return None
    
    test1_path = check_excel_file("test1.xlsx")
    test2_path = check_excel_file("test.xlsx")
    test3_path = check_excel_file("test2.xlsx")
    
    if not test1_path:
        print(f"  ⚠ ВНИМАНИЕ: Файл test1.xlsx не найден!")
        print(f"  Убедитесь, что файл находится в той же папке, что и программа")
    else:
        print(f"  ✓ Файл test1.xlsx найден: {test1_path}")
    
    if not test2_path:
        print(f"  ⚠ ВНИМАНИЕ: Файл test.xlsx не найден!")
        print(f"  Убедитесь, что файл находится в той же папке, что и программа")
    else:
        print(f"  ✓ Файл test.xlsx найден: {test2_path}")
    
    if not test3_path:
        print(f"  ⚠ ВНИМАНИЕ: Файл test2.xlsx не найден!")
        print(f"  Убедитесь, что файл находится в той же папке, что и программа")
    else:
        print(f"  ✓ Файл test2.xlsx найден: {test3_path}")
    
    print("=" * 50 + "\n")
    
    try:
        print("Ищем список заданий...")
        sys.stdout.flush()
        
        # Основной цикл обработки заданий
        while True:
            # Убеждаемся, что мы на главной странице текущего курса
            if f"teacher/courses/{current_course_id}" not in driver.current_url:
                print(f"Переходим на главную страницу курса {current_course_id}...")
                driver.get(current_course_url)
                time.sleep(2)
            
            # Находим список заданий
            lessons_list = find_lessons_list(driver)
            
            if not lessons_list:
                print("⚠ Не удалось найти список заданий!")
                print(f"Текущий URL: {driver.current_url}")
                
                # Проверяем завершение модулей и переход на следующий
                if current_course_id == "770":
                    print("\n" + "=" * 50)
                    print("Модуль 1 (курс 770) завершен!")
                    print("=" * 50)
                    print("Нажмите Enter для перехода на следующий модуль (курс 771)...")
                    print("=" * 50)
                    input("\n>>> Нажмите Enter для продолжения...")
                    current_course_url = MAIN_PAGE_URL
                    current_course_id = "771"
                    current_excel_file = "test.xlsx"
                    selected_module = 2  # Обновляем выбранный модуль
                    print("Переходим на курс 771...")
                    driver.get(current_course_url)
                    time.sleep(3)
                    continue
                elif current_course_id == "771":
                    print("\n" + "=" * 50)
                    print("Модуль 2 (курс 771) завершен!")
                    print("=" * 50)
                    print("Переходим на финальный урок модуля 2 (6107)...")
                    # Переходим на финальный урок модуля 2
                    final_lesson_url = "https://kb.cifrium.ru/teacher/courses/771/lessons/6107"
                    driver.get(final_lesson_url)
                    time.sleep(3)
                    
                    # Нажимаем кнопку задач, если нужно
                    handle_homework_button(driver)
                    time.sleep(2)
                    
                    # Обрабатываем задачи из ftest1.xlsx
                    print("\n" + "=" * 50)
                    print("Обрабатываем задачи из Excel (ftest1.xlsx)...")
                    print("=" * 50)
                    result = process_tasks_from_excel(driver, "ftest1.xlsx")
                    
                    if result == "homework_completed":
                        print("\n" + "=" * 50)
                        print("Контрольный тест модуля 2 завершен!")
                        print("=" * 50)
                        
                        # Проверяем, есть ли еще рандомизированные задачи после контрольного теста
                        # Пробуем распарсить задачу из HTML - если это удалось, значит есть еще задачи
                        print("  Проверяем наличие дополнительных рандомизированных задач...")
                        time.sleep(2)  # Ждем загрузки страницы
                        task_data = parse_task_from_html(driver)
                        if task_data and task_data.get('description') and task_data.get('options'):
                            # Найдена задача - обрабатываем рандомизированные задачи
                            print("\n" + "=" * 50)
                            print("Найдены дополнительные рандомизированные тесты модуля 2!")
                            print("Обрабатываем их с помощью AI...")
                            print("=" * 50)
                            randomized_result = process_randomized_tasks_with_ai(driver, OPENROUTER_API_KEY, OPENROUTER_MODEL)
                            
                            if randomized_result == "homework_completed":
                                print("\n" + "=" * 50)
                                print("Урок 6107 полностью завершен!")
                                print("=" * 50)
                            else:
                                print("\n  Дополнительные тесты модуля 2 обработаны")
                        else:
                            print("  Дополнительных рандомизированных задач не найдено")
                        
                        print("Нажмите Enter для перехода к модулю 3...")
                        print("=" * 50)
                        input("\n>>> Нажмите Enter для продолжения...")
                        current_course_url = MAIN_PAGE_URL_2
                        current_course_id = "772"
                        current_excel_file = "ftest2.xlsx"
                        selected_module = 3
                        print("Переходим на модуль 3...")
                        driver.get(current_course_url)
                        time.sleep(3)
                        
                        # Автоматически переходим на урок 6108 модуля 3
                        print("\n" + "=" * 50)
                        print("Переходим на финальный урок модуля 3 (6108)...")
                        print("=" * 50)
                        final_lesson_url_module3 = "https://kb.cifrium.ru/teacher/courses/772/lessons/6108"
                        driver.get(final_lesson_url_module3)
                        time.sleep(3)
                        
                        # Нажимаем кнопку задач, если нужно
                        handle_homework_button(driver)
                        time.sleep(2)
                        
                        # Обрабатываем задачи из ftest2.xlsx
                        print("\n" + "=" * 50)
                        print("Обрабатываем задачи из Excel (ftest2.xlsx)...")
                        print("=" * 50)
                        result_module3 = process_tasks_from_excel(driver, "ftest2.xlsx")
                        
                        if result_module3 == "homework_completed":
                            print("\n" + "=" * 50)
                            print("Контрольный тест модуля 3 завершен!")
                            print("=" * 50)
                            
                            # Проверяем, есть ли еще рандомизированные задачи после контрольного теста
                            # Пробуем распарсить задачу из HTML - если это удалось, значит есть еще задачи
                            print("  Проверяем наличие дополнительных рандомизированных задач...")
                            time.sleep(2)  # Ждем загрузки страницы
                            task_data_module3 = parse_task_from_html(driver)
                            if task_data_module3 and task_data_module3.get('description') and task_data_module3.get('options'):
                                # Найдена задача - обрабатываем рандомизированные задачи
                                print("\n" + "=" * 50)
                                print("Найдены дополнительные рандомизированные тесты модуля 3!")
                                print("Обрабатываем их с помощью AI...")
                                print("=" * 50)
                                randomized_result_module3 = process_randomized_tasks_with_ai(driver, OPENROUTER_API_KEY, OPENROUTER_MODEL)
                                
                                if randomized_result_module3 == "homework_completed":
                                    print("\n" + "=" * 50)
                                    print("Модуль 3 (курс 772) полностью завершен!")
                                    print("Все модули обработаны!")
                                    print("=" * 50)
                                else:
                                    print("\n  Дополнительные тесты модуля 3 обработаны")
                                    print("\n" + "=" * 50)
                                    print("Модуль 3 (курс 772) завершен!")
                                    print("Все модули обработаны!")
                                    print("=" * 50)
                            else:
                                print("  Дополнительных рандомизированных задач не найдено")
                                print("\n" + "=" * 50)
                                print("Модуль 3 (курс 772) завершен!")
                                print("Все модули обработаны!")
                                print("=" * 50)
                            break
                        else:
                            print("\n  Остаемся на странице задач модуля 3")
                            break
                    else:
                        print("\n  Остаемся на странице задач модуля 2")
                        break
                else:
                    # Модуль 3 завершен
                    print("\n" + "=" * 50)
                    print("Модуль 3 (курс 772) завершен!")
                    print("Все модули обработаны!")
                    print("=" * 50)
                    break
            
            # Извлекаем все задания на текущей странице
            print("Извлекаем задания на текущей странице...")
            all_task_links = get_task_links(driver, lessons_list, current_course_id)
            
            # Фильтруем только невыполненные задания
            incomplete_tasks = [task for task in all_task_links if not task["completed"]]
            completed_tasks = [task for task in all_task_links if task["completed"]]
            
            print(f"Найдено заданий: {len(all_task_links)} (выполнено: {len(completed_tasks)}, не выполнено: {len(incomplete_tasks)})")
            
            # Показываем детальную информацию о выполненных заданиях
            if completed_tasks:
                print(f"\n  ⏭ Пропускаем {len(completed_tasks)} полностью выполненных заданий:")
                for task in completed_tasks:
                    # Извлекаем lesson_id из href для более понятного вывода
                    match = re.search(r'/lessons/(\d+)', task['href'])
                    lesson_id = match.group(1) if match else "unknown"
                    print(f"    - Lesson {lesson_id}: {task['href']}")
            
            # Если все задания выполнены, проверяем кнопку "Load More"
            if not incomplete_tasks and len(all_task_links) > 0:
                print("\n  ✓ Все задания на текущей странице выполнены!")
                # Продолжаем цикл, чтобы проверить кнопку "Load More"
                # (логика проверки кнопки находится ниже)
            
            # Если есть невыполненные задания - обрабатываем первое
            if incomplete_tasks:
                task = incomplete_tasks[0]
                print(f"\nПереходим к невыполненному заданию: {task['href']}")
                
                # Переходим на страницу задания
                driver.get(task['href'])
                
                # Ждем загрузки страницы
                time.sleep(2)
                
                print(f"  На странице задания. URL: {driver.current_url}")
                
                # Обрабатываем Kinescope видео, если оно есть
                print("  Проверяем наличие Kinescope видео...")
                video_result = handle_kinescope_video(driver)
                
                # Если видео не найдено, это означает, что модуль завершен
                # (последнее задание - тест без видео)
                if video_result is False:
                    print("\n" + "=" * 50)
                    print("⚠ На этом задании нет видео - модуль завершен!")
                    print("=" * 50)
                    
                    # Проверяем завершение модулей и переход на следующий
                    if current_course_id == "770":
                        print("Модуль 1 (курс 770) завершен!")
                        print("=" * 50)
                        print("Нажмите Enter для перехода на следующий модуль (курс 771)...")
                        print("=" * 50)
                        input("\n>>> Нажмите Enter для продолжения...")
                        current_course_url = MAIN_PAGE_URL
                        current_course_id = "771"
                        current_excel_file = "test.xlsx"
                        selected_module = 2  # Обновляем выбранный модуль
                        print("Переходим на курс 771...")
                        driver.get(current_course_url)
                        time.sleep(3)
                        continue
                    elif current_course_id == "771":
                        print("Модуль 2 (курс 771) завершен!")
                        print("=" * 50)
                        print("Переходим на финальный урок модуля 2 (6107)...")
                        # Переходим на финальный урок модуля 2
                        final_lesson_url = "https://kb.cifrium.ru/teacher/courses/771/lessons/6107"
                        driver.get(final_lesson_url)
                        time.sleep(3)
                        
                        # Нажимаем кнопку задач, если нужно
                        handle_homework_button(driver)
                        time.sleep(2)
                        
                        # Обрабатываем задачи из ftest1.xlsx
                        print("\n" + "=" * 50)
                        print("Обрабатываем задачи из Excel (ftest1.xlsx)...")
                        print("=" * 50)
                        result = process_tasks_from_excel(driver, "ftest1.xlsx")
                        
                        if result == "homework_completed":
                            print("\n" + "=" * 50)
                            print("Контрольный тест модуля 2 завершен!")
                            print("=" * 50)
                            
                            # Проверяем, есть ли еще рандомизированные задачи после контрольного теста
                            current_url_after_test = driver.current_url
                            if "/trainings/" in current_url_after_test or "/tasks/" in current_url_after_test:
                                # Мы все еще на странице задач - обрабатываем рандомизированные задачи
                                print("\n" + "=" * 50)
                                print("Обрабатываем дополнительные рандомизированные тесты модуля 2...")
                                print("=" * 50)
                                randomized_result = process_randomized_tasks_with_ai(driver, OPENROUTER_API_KEY, OPENROUTER_MODEL)
                                
                                if randomized_result == "homework_completed":
                                    print("\n" + "=" * 50)
                                    print("Урок 6107 полностью завершен!")
                                    print("=" * 50)
                                else:
                                    print("\n  Дополнительные тесты модуля 2 обработаны")
                            
                            print("Нажмите Enter для перехода к модулю 3...")
                            print("=" * 50)
                            input("\n>>> Нажмите Enter для продолжения...")
                            current_course_url = MAIN_PAGE_URL_2
                            current_course_id = "772"
                            current_excel_file = "ftest2.xlsx"
                            selected_module = 3
                            print("Переходим на модуль 3...")
                            driver.get(current_course_url)
                            time.sleep(3)
                            
                            # Автоматически переходим на урок 6108 модуля 3
                            print("\n" + "=" * 50)
                            print("Переходим на финальный урок модуля 3 (6108)...")
                            print("=" * 50)
                            final_lesson_url_module3 = "https://kb.cifrium.ru/teacher/courses/772/lessons/6108"
                            driver.get(final_lesson_url_module3)
                            time.sleep(3)
                            
                            # Нажимаем кнопку задач, если нужно
                            handle_homework_button(driver)
                            time.sleep(2)
                            
                            # Обрабатываем задачи из ftest2.xlsx
                            print("\n" + "=" * 50)
                            print("Обрабатываем задачи из Excel (ftest2.xlsx)...")
                            print("=" * 50)
                            result_module3 = process_tasks_from_excel(driver, "ftest2.xlsx")
                            
                            if result_module3 == "homework_completed":
                                print("\n" + "=" * 50)
                                print("Контрольный тест модуля 3 завершен!")
                                print("=" * 50)
                                
                                # Проверяем, есть ли еще рандомизированные задачи после контрольного теста
                                current_url_after_test_module3 = driver.current_url
                                if "/trainings/" in current_url_after_test_module3 or "/tasks/" in current_url_after_test_module3:
                                    # Мы все еще на странице задач - обрабатываем рандомизированные задачи
                                    print("\n" + "=" * 50)
                                    print("Обрабатываем дополнительные рандомизированные тесты модуля 3...")
                                    print("=" * 50)
                                    randomized_result_module3 = process_randomized_tasks_with_ai(driver, OPENROUTER_API_KEY, OPENROUTER_MODEL)
                                    
                                    if randomized_result_module3 == "homework_completed":
                                        print("\n" + "=" * 50)
                                        print("Модуль 3 (курс 772) полностью завершен!")
                                        print("Все модули обработаны!")
                                        print("=" * 50)
                                    else:
                                        print("\n  Дополнительные тесты модуля 3 обработаны")
                                        print("\n" + "=" * 50)
                                        print("Модуль 3 (курс 772) завершен!")
                                        print("Все модули обработаны!")
                                        print("=" * 50)
                                else:
                                    print("\n" + "=" * 50)
                                    print("Модуль 3 (курс 772) завершен!")
                                    print("Все модули обработаны!")
                                    print("=" * 50)
                                break
                            else:
                                print("\n  Остаемся на странице задач модуля 3")
                                break
                        else:
                            print("\n  Остаемся на странице задач модуля 2")
                            break
                    else:
                        # Мы уже на курсе 772, завершаем работу
                        print("Модуль 3 (курс 772) завершен!")
                        print("Все модули обработаны!")
                        print("=" * 50)
                        break
                elif video_result is True:
                    # Видео обработано успешно, переходим к кнопке задач
                    print("  Видео обработано, ищем кнопку задач...")
                    handle_homework_button(driver)
                    
                    # Проверяем, на какой странице мы находимся
                    current_url = driver.current_url
                    if "/tasks" in current_url:
                        print("  Находимся на странице задач")
                        
                        # Обрабатываем все задачи текущего homework из Excel
                        print("\n" + "=" * 50)
                        print(f"Обрабатываем задачи из Excel ({current_excel_file})...")
                        print("=" * 50)
                        result = process_tasks_from_excel(driver, current_excel_file)
                        
                        if result == "homework_completed":
                            # Домашнее задание завершено, вернулись на страницу курса
                            print("\n  Домашнее задание завершено, продолжаем с другими заданиями")
                            # Полностью перезагружаем страницу, чтобы обновить статус заданий
                            driver.get(current_course_url)
                            time.sleep(3)  # Ждем обновления страницы
                            
                            # Принудительно обновляем страницу для обновления статуса заданий
                            driver.refresh()
                            time.sleep(2)
                            
                            # Продолжаем основной цикл для обработки других заданий
                            # Список заданий будет обновлен в начале следующей итерации цикла
                            continue
                        else:
                            print("\n  Остаемся на странице задач")
                            # Не возвращаемся на главную, остаемся на tasks странице
                            break  # Выходим из цикла, так как на tasks странице нет списка заданий
                    else:
                        # Возвращаемся на главную страницу для следующей проверки
                        print("  Возвращаемся на главную страницу...")
                        driver.get(current_course_url)
                        time.sleep(2)
                        continue
                
                # Если видео не было обработано (None или другая ошибка), возвращаемся на главную
                print("  Возвращаемся на главную страницу...")
                driver.get(current_course_url)
                time.sleep(2)
                
                # Продолжаем цикл, чтобы проверить задания снова
                continue
            
            # Если все задания выполнены, проверяем кнопку "Показать ещё"
            print("\n✓ Все задания на текущей странице выполнены!")
            
            # Проверяем, есть ли кнопка "Показать ещё" и не disabled ли она
            load_more_button = find_load_more_button(driver, lessons_list)
            
            if load_more_button:
                print("Найдена кнопка 'Показать ещё'. Нажимаем...")
                if click_load_more_button(driver, load_more_button):
                    print("Кнопка нажата. Ждем загрузки новых заданий...")
                    time.sleep(2)
                    # Продолжаем цикл, чтобы обработать новые задания
                    continue
                else:
                    print("⚠ Не удалось нажать на кнопку")
                    break
            else:
                print("Кнопка 'Показать ещё' не найдена или отключена.")
                
                # Проверяем завершение модулей и переход на следующий
                if current_course_id == "770":
                    print("\n" + "=" * 50)
                    print("Модуль 1 (курс 770) завершен!")
                    print("=" * 50)
                    print("Нажмите Enter для перехода на следующий модуль (курс 771)...")
                    print("=" * 50)
                    input("\n>>> Нажмите Enter для продолжения...")
                    current_course_url = MAIN_PAGE_URL
                    current_course_id = "771"
                    current_excel_file = "test.xlsx"
                    selected_module = 2  # Обновляем выбранный модуль
                    print("Переходим на курс 771...")
                    driver.get(current_course_url)
                    time.sleep(3)
                    continue
                elif current_course_id == "771":
                    print("\n" + "=" * 50)
                    print("Модуль 2 (курс 771) завершен!")
                    print("=" * 50)
                    print("Переходим на финальный урок модуля 2 (6107)...")
                    # Переходим на финальный урок модуля 2
                    final_lesson_url = "https://kb.cifrium.ru/teacher/courses/771/lessons/6107"
                    driver.get(final_lesson_url)
                    time.sleep(3)
                    
                    # Нажимаем кнопку задач, если нужно
                    handle_homework_button(driver)
                    time.sleep(2)
                    
                    # Обрабатываем задачи из ftest1.xlsx
                    print("\n" + "=" * 50)
                    print("Обрабатываем задачи из Excel (ftest1.xlsx)...")
                    print("=" * 50)
                    result = process_tasks_from_excel(driver, "ftest1.xlsx")
                    
                    if result == "homework_completed":
                        print("\n" + "=" * 50)
                        print("Контрольный тест модуля 2 завершен!")
                        print("=" * 50)
                        
                        # Проверяем, есть ли еще рандомизированные задачи после контрольного теста
                        # Пробуем распарсить задачу из HTML - если это удалось, значит есть еще задачи
                        print("  Проверяем наличие дополнительных рандомизированных задач...")
                        time.sleep(2)  # Ждем загрузки страницы
                        task_data = parse_task_from_html(driver)
                        if task_data and task_data.get('description') and task_data.get('options'):
                            # Найдена задача - обрабатываем рандомизированные задачи
                            print("\n" + "=" * 50)
                            print("Найдены дополнительные рандомизированные тесты модуля 2!")
                            print("Обрабатываем их с помощью AI...")
                            print("=" * 50)
                            randomized_result = process_randomized_tasks_with_ai(driver, OPENROUTER_API_KEY, OPENROUTER_MODEL)
                            
                            if randomized_result == "homework_completed":
                                print("\n" + "=" * 50)
                                print("Урок 6107 полностью завершен!")
                                print("=" * 50)
                            else:
                                print("\n  Дополнительные тесты модуля 2 обработаны")
                        else:
                            print("  Дополнительных рандомизированных задач не найдено")
                        
                        print("Нажмите Enter для перехода к модулю 3...")
                        print("=" * 50)
                        input("\n>>> Нажмите Enter для продолжения...")
                        current_course_url = MAIN_PAGE_URL_2
                        current_course_id = "772"
                        current_excel_file = "ftest2.xlsx"
                        selected_module = 3
                        print("Переходим на модуль 3...")
                        driver.get(current_course_url)
                        time.sleep(3)
                        
                        # Автоматически переходим на урок 6108 модуля 3
                        print("\n" + "=" * 50)
                        print("Переходим на финальный урок модуля 3 (6108)...")
                        print("=" * 50)
                        final_lesson_url_module3 = "https://kb.cifrium.ru/teacher/courses/772/lessons/6108"
                        driver.get(final_lesson_url_module3)
                        time.sleep(3)
                        
                        # Нажимаем кнопку задач, если нужно
                        handle_homework_button(driver)
                        time.sleep(2)
                        
                        # Обрабатываем задачи из ftest2.xlsx
                        print("\n" + "=" * 50)
                        print("Обрабатываем задачи из Excel (ftest2.xlsx)...")
                        print("=" * 50)
                        result_module3 = process_tasks_from_excel(driver, "ftest2.xlsx")
                        
                        if result_module3 == "homework_completed":
                            print("\n" + "=" * 50)
                            print("Контрольный тест модуля 3 завершен!")
                            print("=" * 50)
                            
                            # Проверяем, есть ли еще рандомизированные задачи после контрольного теста
                            # Пробуем распарсить задачу из HTML - если это удалось, значит есть еще задачи
                            print("  Проверяем наличие дополнительных рандомизированных задач...")
                            time.sleep(2)  # Ждем загрузки страницы
                            task_data_module3 = parse_task_from_html(driver)
                            if task_data_module3 and task_data_module3.get('description') and task_data_module3.get('options'):
                                # Найдена задача - обрабатываем рандомизированные задачи
                                print("\n" + "=" * 50)
                                print("Найдены дополнительные рандомизированные тесты модуля 3!")
                                print("Обрабатываем их с помощью AI...")
                                print("=" * 50)
                                randomized_result_module3 = process_randomized_tasks_with_ai(driver, OPENROUTER_API_KEY, OPENROUTER_MODEL)
                                
                                if randomized_result_module3 == "homework_completed":
                                    print("\n" + "=" * 50)
                                    print("Модуль 3 (курс 772) полностью завершен!")
                                    print("Все модули обработаны!")
                                    print("=" * 50)
                                else:
                                    print("\n  Дополнительные тесты модуля 3 обработаны")
                                    print("\n" + "=" * 50)
                                    print("Модуль 3 (курс 772) завершен!")
                                    print("Все модули обработаны!")
                                    print("=" * 50)
                            else:
                                print("  Дополнительных рандомизированных задач не найдено")
                                print("\n" + "=" * 50)
                                print("Модуль 3 (курс 772) завершен!")
                                print("Все модули обработаны!")
                                print("=" * 50)
                            break
                        else:
                            print("\n  Остаемся на странице задач модуля 3")
                            break
                    else:
                        print("\n  Остаемся на странице задач модуля 2")
                        break
                elif current_course_id == "772":
                    # Модуль 3 завершен
                    print("\n" + "=" * 50)
                    print("Модуль 3 (курс 772) завершен!")
                    print("Все модули обработаны!")
                    print("=" * 50)
                    break
                else:
                    print("Все задания обработаны!")
                    break
        
        print("\n✓ Все задания обработаны!")
        
    except KeyboardInterrupt:
        interrupted = True
        print("\n\n" + "=" * 50)
        print("⚠ ПРОЦЕСС ПРЕРВАН ПОЛЬЗОВАТЕЛЕМ (Ctrl+C)")
        print("=" * 50)
        print("Браузер остается открытым для ручной работы.")
        print("Закройте браузер вручную когда закончите.")
        print("=" * 50)
        # Не закрываем браузер при Ctrl+C
        
    except Exception as e:
        print(f"Произошла ошибка: {e}")
        import traceback
        traceback.print_exc()
    
    finally:
        # Браузер остается открытым для ручной работы
        if driver:
            print("\n" + "=" * 50)
            print("✓ Скрипт завершен. Браузер остается открытым.")
            print("Закройте браузер вручную когда закончите работу.")
            print("=" * 50)
            # Не закрываем браузер - оставляем открытым
            # driver.quit()  # Закомментировано по запросу пользователя
            # Благодаря опции detach=True в ChromeOptions, браузер останется открытым
            # даже после завершения скрипта
            
            # Ждем, чтобы пользователь мог увидеть результат
            print("\nНажмите Enter для завершения программы (браузер останется открытым)...")
            try:
                input()
                print("Программа завершена. Браузер остается открытым благодаря опции detach=True.")
            except KeyboardInterrupt:
                print("\n\nПрограмма завершена пользователем. Браузер остается открытым.")
                pass
            except:
                pass

if __name__ == "__main__":
    main()

