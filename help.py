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

# Глобальная переменная для driver, чтобы можно было закрыть его при Ctrl+C
global_driver = None

# URL главной страницы
MAIN_PAGE_URL = "https://kb.cifrium.ru/teacher/courses/771"  # Модуль 2
MAIN_PAGE_URL_2 = "https://kb.cifrium.ru/teacher/courses/772"  # Следующий курс
HOME_URL = "https://kb.cifrium.ru/"
LOGIN_URL = "https://kb.cifrium.ru/user/login"

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
            return True
        else:
            print("  ⚠ Не удалось извлечь lesson ID из URL")
            return False
            
    except Exception as e:
        print(f"  ⚠ Ошибка при переходе на tasks страницу: {e}")
        return False

def get_task_form(driver, timeout=10):
    """Получает форму задачи с ожиданием загрузки"""
    wait = WebDriverWait(driver, timeout)
    return wait.until(EC.presence_of_element_located((By.ID, "taskForm")))

def detect_task_type(driver):
    """Определяет тип задачи на странице"""
    try:
        # Ждем загрузки формы задачи
        print("  Ожидаем загрузки формы задачи...")
        task_form = get_task_form(driver)
        print("  Форма задачи загружена")
        
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
    answer - значение (value) для выбора"""
    try:
        task_form = get_task_form(driver)
        radios = task_form.find_elements(By.CSS_SELECTOR, "input[type='radio']")
        
        print(f"  Найдено радио-кнопок: {len(radios)}")
        print(f"  Выбираем значение: {answer}")
        
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
                        
                        // Также пробуем кликнуть на родительский элемент
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
                            # Ищем родительский div с классом styled__Root
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
        
        print(f"  ⚠ Не найдена радио-кнопка со значением: {answer}")
        return False
        
    except Exception as e:
        print(f"  ⚠ Ошибка при обработке radio задачи: {e}")
        return False

def handle_drag_and_drop_task(driver, mappings):
    """Обрабатывает задачу типа drag and drop (перетаскивание)
    mappings - словарь {текст_цели: текст_элемента} или список кортежей [(текст_цели, текст_элемента)]"""
    try:
        task_form = get_task_form(driver)
        
        # Находим все перетаскиваемые элементы
        draggable_elements = task_form.find_elements(By.CSS_SELECTOR, "[draggable='true']")
        print(f"  Найдено перетаскиваемых элементов: {len(draggable_elements)}")
        
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
            
            # Находим элемент для перетаскивания по тексту
            # Ищем во всех возможных контейнерах опций, не только с draggable='true'
            source_element = None
            
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
                        try:
                            parent = container.find_element(By.XPATH, "./ancestor::div[contains(@class, 'LinkTaskRow_linkRowContent__XBn6u')]")
                            # Контейнер уже в drop area, пропускаем
                            continue
                        except:
                            # Контейнер еще не перемещен, проверяем текст
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
            for target in target_areas:
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
                        print(f"      Найдена целевая область: '{text[:50]}...'")
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
                    success = driver.execute_script("""
                        var source = arguments[0];
                        var target = arguments[1];
                        
                        try {
                            // Проверяем, не находится ли элемент уже в целевой области
                            if (target.contains(source) || target.contains(source.parentElement)) {
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
                            
                            // 1. Инициируем dragstart на исходном элементе
                            var dragStartEvent = new DragEvent('dragstart', { 
                                bubbles: true, 
                                cancelable: true,
                                dataTransfer: dataTransfer
                            });
                            draggableElement.dispatchEvent(dragStartEvent);
                            
                            // 2. Инициируем dragover на целевой области
                            var dragOverEvent = new DragEvent('dragover', { 
                                bubbles: true, 
                                cancelable: true,
                                dataTransfer: dataTransfer
                            });
                            dragOverEvent.preventDefault(); // Разрешаем drop
                            target.dispatchEvent(dragOverEvent);
                            
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
                            
                            // 7. Удаляем исходный элемент
                            optionContainer.remove();
                            
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
                                
                                // Получаем значение из перетащенного элемента
                                var optionText = clone.textContent.trim() || 
                                                clone.querySelector('.MathContent_content')?.textContent.trim() || 
                                                clone.querySelector('span')?.textContent.trim() || '';
                                
                                // Пробуем найти data-id или другой идентификатор
                                var optionId = clone.getAttribute('data-id') || 
                                              clone.querySelector('[data-id]')?.getAttribute('data-id') ||
                                              draggableElement.getAttribute('data-id') ||
                                              optionContainer.getAttribute('data-id') || '';
                                
                                var valueToSet = optionId || optionText;
                                
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
                                    console.log('⚠ Input не найден в drop area, ищем в родительских элементах...');
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
                    """, source_element, target_area)
                    
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
                            matched_count += 1
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
            try:
                task_form = get_task_form(driver)
                driver.execute_script("""
                    var form = arguments[0];
                    if (form) {
                        console.log('=== ФИНАЛЬНОЕ ОБНОВЛЕНИЕ ВСЕХ ПОЛЕЙ ===');
                        
                        // Обновляем все drop areas
                        var dropAreas = form.querySelectorAll('.LinkTaskRow_linkRowContent__XBn6u');
                        dropAreas.forEach(function(dropArea, index) {
                            var option = dropArea.querySelector('.OptionsSlide_option__PBAys, .styled__Wrapper-cixSOf');
                            var inputInArea = dropArea.querySelector('input[type="hidden"]');
                            
                            if (option && inputInArea) {
                                var optionText = option.textContent.trim() || 
                                                option.querySelector('.MathContent_content')?.textContent.trim() || 
                                                option.querySelector('span')?.textContent.trim() || '';
                                var optionId = option.getAttribute('data-id') || 
                                              option.querySelector('[data-id]')?.getAttribute('data-id') || '';
                                var valueToSet = optionId || optionText;
                                
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
                                }
                            } else {
                                console.log('⚠ Поле', index, 'не найдено (option:', !!option, 'input:', !!inputInArea, ')');
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
            time.sleep(0.8)  # Уменьшено время ожидания для обработки формы
        else:
            print("  Задача уже решена, ищем кнопку 'Дальше'...")
            time.sleep(0.3)  # Небольшая задержка для стабильности
        
        # Ищем кнопку "Дальше"
        # Если кнопка не найдена - это последний вопрос домашнего задания
        wait = WebDriverWait(driver, 1)  # Уменьшено время ожидания до 1 секунды
        try:
            # Ищем кнопку "Дальше" по нескольким способам
            next_button = None
            
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
                
                # Кликаем на кнопку
                try:
                    next_button.click()
                    print("  ✓ Нажата кнопка 'Дальше'")
                except:
                    driver.execute_script("arguments[0].click();", next_button)
                    print("  ✓ Нажата кнопка 'Дальше' (через JS)")
                
                time.sleep(0.3)  # Уменьшено время ожидания перехода
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
                    # Ищем следующий sibling div с классом, содержащим styled__Label или MathContent_root
                    label_div = radio.find_element(By.XPATH, "./following-sibling::div[contains(@class, 'styled__Label') or contains(@class, 'MathContent_root')]")
                    # Внутри может быть span с классом MathContent_content или MathContent_content__2a8XE
                    try:
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
    for i, (radio, value, label_text, label_normalized, _) in enumerate(candidates[:3]):  # Показываем первые 3
        print(f"      {i+1}. value={value}, text='{label_text[:50]}...'")
    
    # Сортируем по длине (сначала самые длинные) для приоритета полных ответов
    candidates.sort(key=lambda x: x[4], reverse=True)
    
    print(f"    [DEBUG] Ищем совпадение для: '{answer_text[:50]}...' (нормализовано: '{answer_normalized[:50]}...')")
    
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
            parent = checkbox.find_element(By.XPATH, "./..")
            label_text = parent.text.strip()
            value = checkbox.get_attribute("value")
            label_normalized = ' '.join(label_text.lower().split())
            checkbox_candidates.append((value, label_text, label_normalized, len(label_normalized)))
        except:
            continue
    
    # Сортируем по длине (сначала самые длинные) для приоритета полных ответов
    checkbox_candidates.sort(key=lambda x: x[3], reverse=True)
    
    for answer_part in answer_parts:
        answer_normalized = ' '.join(answer_part.lower().split())
        best_match = None
        
        # 1. Ищем точное совпадение
        for value, label_text, label_normalized, _ in checkbox_candidates:
            if answer_normalized == label_normalized:
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
                            best_match = value
                            break
        
        # 3. Если не нашли вариант с полным ответом, ищем частичное совпадение (только если >= 90%)
        if not best_match:
            for value, label_text, label_normalized, label_len in checkbox_candidates:
                if len(answer_normalized) >= len(label_normalized):
                    if label_normalized in answer_normalized:
                        match_ratio = len(label_normalized) / len(answer_normalized)
                        if match_ratio >= 0.9 and answer_normalized.startswith(label_normalized):
                            best_match = value
                            break
        
        if best_match:
            if best_match not in selected_values:
                selected_values.append(best_match)
                # Находим текст для вывода
                for value, label_text, _, _ in checkbox_candidates:
                    if value == best_match:
                        print(f"    Найден чекбокс для '{answer_part[:50]}...': '{label_text[:50]}...' (value: {best_match})")
                        break
    
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

def process_tasks_from_excel(driver, excel_path="test.xlsx"):
    """Обрабатывает все задачи текущего домашнего задания из Excel"""
    try:
        # Извлекаем lesson_id из текущего URL
        current_url = driver.current_url
        print(f"\n  Текущий URL: {current_url}")
        
        match = re.search(r'/lessons/(\d+)/tasks', current_url)
        if not match:
            print("  ⚠ Не удалось извлечь lesson_id из URL")
            return False
        
        lesson_id = match.group(1)
        print(f"  Найден lesson_id: {lesson_id}")
        
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
        
        for col in df.columns:
            col_lower = col.lower()
            if 'homework' in col_lower:
                homework_column = col
            elif 'answer' in col_lower or 'ответ' in col_lower:
                answer_column = col
        
        if homework_column is None:
            print("  ⚠ Не найдена колонка 'Homework' в Excel")
            return False
        
        if answer_column is None:
            print("  ⚠ Не найдена колонка 'Answer' в Excel")
            return False
        
        # Фильтруем задачи по текущему homework ID
        # Преобразуем homework колонку в строки для сравнения
        df[homework_column] = df[homework_column].astype(str)
        homework_tasks = df[df[homework_column] == lesson_id].copy()
        
        if len(homework_tasks) == 0:
            print(f"  ⚠ Не найдено задач для homework ID: {lesson_id}")
            print(f"  Доступные homework ID в Excel: {df[homework_column].unique().tolist()}")
            return False
        
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
            
            # ВРЕМЕННО ОТКЛЮЧЕНО: Проверка зацикливания
            # Проверяем, не обработали ли мы уже эту задачу
            # if current_task_id and current_task_id in processed_task_ids:
            #     print(f"\n  ⚠ ВНИМАНИЕ: Задача с ID {current_task_id} уже была обработана!")
            #     print(f"  Пропускаем эту задачу и переходим к следующей.")
            #     # Обновляем previous_url и увеличиваем task_index
            #     previous_url = current_url
            #     task_index += 1
            #     continue
            
            # ВРЕМЕННО ОТКЛЮЧЕНО: Проверка зацикливания
            # Проверяем зацикливание: сравниваем ID задач, если они есть
            # if previous_url is not None and task_index > 0:
            #     if current_task_id and previous_task_id:
            #         # Если ID задач одинаковые, значит мы на той же задаче
            #         if current_task_id == previous_task_id:
            #             print(f"\n  ⚠ ВНИМАНИЕ: ID задачи не изменился после предыдущей задачи!")
            #             print(f"  Текущий URL: {current_url}")
            #             print(f"  Предыдущий URL: {previous_url}")
            #             print(f"  ID задачи: {current_task_id}")
            #             print(f"  Возможно, мы зациклились. Пропускаем эту задачу и переходим к следующей.")
            #             # Обновляем previous_url перед переходом к следующей задаче
            #             previous_url = current_url
            #             task_index += 1
            #             continue
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
            
            # Определяем тип задачи на странице
            print("\n  Определяем тип задачи на странице...")
            task_type = detect_task_type(driver)
            
            # Проверяем ответ из Excel - если это список/массив, это должна быть checkbox задача
            # Это важно, так как некоторые страницы могут иметь и radio и checkbox элементы
            if answer_text and (answer_text.strip().startswith('[') or 
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
            
            if task_type == "unknown":
                print("  ⚠ Не удалось определить тип задачи")
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
                        print(f"  ✓ Переход подтвержден (URL изменился)")
                        previous_url = url_after_next
                        task_index += 1
                    else:
                        # URL не изменился - возможно это была последняя задача
                        if "/tasks" not in url_after_next:
                            print(f"  ✓ Похоже, мы вернулись на страницу курса - все задачи выполнены")
                            return "homework_completed"
                        else:
                            print(f"  ⚠ URL не изменился, но мы все еще на странице задач")
                            print(f"  Увеличиваем индекс чтобы избежать зацикливания")
                            previous_url = url_after_next
                            task_index += 1
                    continue
                except:
                    print("  ⚠ Задача не решена и тип не определен, пропускаем")
                    previous_url = driver.current_url  # Обновляем previous_url
                    task_index += 1
                    continue
            
            # Подготавливаем ответ в зависимости от типа задачи
            task_answer = None
            answer_text = str(task_data[answer_column]).strip()
            
            # Пропускаем пустые ответы
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
                                try:
                                    label_div = radio.find_element(By.XPATH, "./following-sibling::div[contains(@class, 'styled__Label') or contains(@class, 'MathContent_root')]")
                                    try:
                                        span = label_div.find_element(By.XPATH, ".//span[contains(@class, 'MathContent_content')]")
                                        label_text = span.text.strip()[:50]
                                    except:
                                        label_text = label_div.text.strip()[:50]
                                except:
                                    parent = radio.find_element(By.XPATH, "./..")
                                    label_text = parent.text.strip()[:50]
                                print(f"      - value={value}: '{label_text}...'")
                            except:
                                pass
                    except:
                        pass
                    previous_url = driver.current_url  # Обновляем previous_url
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
                            task_index += 1
                            print(f"  [DEBUG] Увеличен task_index до: {task_index}")
                        elif not task_id_before and task_id_after:
                            # Перешли с главной страницы на страницу задачи - это нормально
                            # Это означает, что мы обработали первую задачу из списка и перешли на её страницу
                            print(f"  ✓ Переход на страницу задачи подтвержден")
                            print(f"  [DEBUG] URL до: {url_before}")
                            print(f"  [DEBUG] URL после: {url_after}")
                            print(f"  [DEBUG] ID задачи: {task_id_after}")
                            # Добавляем текущую задачу в список обработанных
                            processed_task_ids.add(task_id_after)
                            previous_url = url_after  # Обновляем previous_url
                            print(f"  [DEBUG] Обновлен previous_url: {previous_url}")
                            # Увеличиваем task_index, потому что мы обработали задачу из списка
                            task_index += 1
                            print(f"  [DEBUG] Увеличен task_index до: {task_index} (первая задача обработана)")
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
    print("  2 - Модуль 2 (курс 771, файл test.xlsx)")
    print("  3 - Модуль 3 (курс 772, файл test2.xlsx)")
    print("=" * 50)
    
    while True:
        try:
            choice = input("\n>>> Введите номер модуля (2 или 3): ").strip()
            if choice == "2":
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
                print("  ⚠ Неверный выбор! Введите 2 или 3")
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
    elif MAIN_PAGE_URL in current_url or MAIN_PAGE_URL_2 in current_url or "teacher/courses" in current_url:
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
        
        if MAIN_PAGE_URL in current_url or MAIN_PAGE_URL_2 in current_url or "teacher/courses" in current_url:
            print("✓ Отлично! Вы залогинены и на нужной странице.")
        else:
            print(f"⚠ Текущий URL: {current_url}")
            print("Переходим на целевую страницу...")
            driver.get(initial_course_url)
            time.sleep(3)
            
            final_url = driver.current_url
            if MAIN_PAGE_URL in final_url or MAIN_PAGE_URL_2 in final_url or "teacher/courses" in final_url:
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
    if MAIN_PAGE_URL in final_url or MAIN_PAGE_URL_2 in final_url or "teacher/courses" in final_url:
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
    
    test1_path = check_excel_file("test.xlsx")
    test2_path = check_excel_file("test2.xlsx")
    
    if not test1_path:
        print(f"  ⚠ ВНИМАНИЕ: Файл test.xlsx не найден!")
        print(f"  Убедитесь, что файл находится в той же папке, что и программа")
    else:
        print(f"  ✓ Файл test.xlsx найден: {test1_path}")
    
    if not test2_path:
        print(f"  ⚠ ВНИМАНИЕ: Файл test2.xlsx не найден!")
        print(f"  Убедитесь, что файл находится в той же папке, что и программа")
    else:
        print(f"  ✓ Файл test2.xlsx найден: {test2_path}")
    
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
                
                # Если мы на курсе 771 и не нашли список, возможно модуль 2 завершен
                if current_course_id == "771":
                    print("\n" + "=" * 50)
                    print("Модуль 2 (курс 771) завершен!")
                    print("=" * 50)
                    print("Нажмите Enter для перехода на следующий модуль (курс 772)...")
                    print("=" * 50)
                    input("\n>>> Нажмите Enter для продолжения...")
                    current_course_url = MAIN_PAGE_URL_2
                    current_course_id = "772"
                    current_excel_file = "test2.xlsx"
                    selected_module = 3  # Обновляем выбранный модуль
                    print("Переходим на курс 772...")
                    driver.get(current_course_url)
                    time.sleep(3)
                    continue
                else:
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
                    
                    # Если мы на курсе 771 (модуль 2), переходим на курс 772 (модуль 3)
                    if current_course_id == "771":
                        print("Модуль 2 (курс 771) завершен!")
                        print("=" * 50)
                        print("Нажмите Enter для перехода на следующий модуль (курс 772)...")
                        print("=" * 50)
                        input("\n>>> Нажмите Enter для продолжения...")
                        current_course_url = MAIN_PAGE_URL_2
                        current_course_id = "772"
                        current_excel_file = "test2.xlsx"
                        selected_module = 3  # Обновляем выбранный модуль
                        print("Переходим на курс 772...")
                        driver.get(current_course_url)
                        time.sleep(3)
                        # Продолжаем цикл для обработки заданий нового курса
                        continue
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
                
                # Если мы на курсе 771, проверяем, завершен ли модуль 2
                if current_course_id == "771":
                    print("\n" + "=" * 50)
                    print("Модуль 2 (курс 771) завершен!")
                    print("=" * 50)
                    print("Нажмите Enter для перехода на следующий модуль (курс 772)...")
                    print("=" * 50)
                    input("\n>>> Нажмите Enter для продолжения...")
                    current_course_url = MAIN_PAGE_URL_2
                    current_course_id = "772"
                    current_excel_file = "test2.xlsx"
                    selected_module = 3  # Обновляем выбранный модуль
                    print("Переходим на курс 772...")
                    driver.get(current_course_url)
                    time.sleep(3)
                    # Продолжаем цикл для обработки заданий нового курса
                    continue
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

