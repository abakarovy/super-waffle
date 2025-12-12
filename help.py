from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.chrome.options import Options
import time
import os
import sys

# URL главной страницы
MAIN_PAGE_URL = "https://kb.cifrium.ru/teacher/courses/771"

def setup_driver():
    """Настройка и создание драйвера Chrome"""
    print("Настраиваем Chrome драйвер...")
    chrome_options = Options()
    
    # Используем ваш существующий профиль Chrome для сохранения сессии
    user_data_dir = os.path.join(os.path.expanduser("~"), "AppData", "Local", "Google", "Chrome", "User Data")
    print(f"Используем профиль Chrome: {user_data_dir}")
    print("ВАЖНО: Закройте ВСЕ окна Chrome перед запуском скрипта!")
    
    chrome_options.add_argument(f"--user-data-dir={user_data_dir}")
    chrome_options.add_argument("--profile-directory=Default")
    
    # Раскомментируйте следующую строку, если хотите запускать браузер в фоновом режиме
    # chrome_options.add_argument("--headless")
    chrome_options.add_argument("--disable-blink-features=AutomationControlled")
    chrome_options.add_experimental_option("excludeSwitches", ["enable-automation"])
    chrome_options.add_experimental_option('useAutomationExtension', False)
    
    print("Создаем экземпляр браузера...")
    try:
        driver = webdriver.Chrome(options=chrome_options)
        print("✓ Браузер успешно открыт!")
        driver.maximize_window()
        return driver
    except Exception as e:
        error_msg = str(e)
        print(f"\n✗ ОШИБКА при создании браузера: {error_msg}")
        
        if "user data directory is already in use" in error_msg.lower() or "cannot connect" in error_msg.lower():
            print("\n⚠ Chrome все еще запущен!")
            print("Пожалуйста, закройте ВСЕ окна Chrome и попробуйте снова.")
        else:
            print("\nВозможные причины:")
            print("1. ChromeDriver не установлен или не в PATH")
            print("2. Несовместимая версия ChromeDriver")
            print("3. Проблемы с правами доступа")
        
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

def get_task_links(driver, lessons_list):
    """Извлекает все ссылки на задания из списка"""
    try:
        # Находим все элементы <a> внутри списка заданий
        task_links = lessons_list.find_elements(By.TAG_NAME, "a")
        
        links = []
        for link in task_links:
            href = link.get_attribute("href")
            if href and "/teacher/courses/771/lessons/" in href:
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
    """Проверяет, выполнено ли задание (наличие div с классом Item_status__)"""
    try:
        # Ищем div с классом, начинающимся с "Item_status__"
        status_div = link_element.find_element(
            By.XPATH, 
            ".//div[contains(@class, 'Item_status__')]"
        )
        return True
    except:
        return False

def main():
    print("=" * 50)
    print("Запуск скрипта...")
    print("=" * 50)
    print("\n⚠ ВАЖНО: Закройте ВСЕ окна Chrome перед запуском!")
    print("=" * 50)
    print()
    
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
    
    print("\n" + "=" * 50)
    print("НАЧИНАЕМ НАВИГАЦИЮ")
    print("=" * 50)
    sys.stdout.flush()
    
    try:
        print(f"Открываем главную страницу: {MAIN_PAGE_URL}")
        print("Вызываем driver.get()...")
        sys.stdout.flush()
        
        driver.get(MAIN_PAGE_URL)
        print("✓ driver.get() выполнен успешно!")
        sys.stdout.flush()
        
        # Ждем загрузки страницы
        print("Ждем загрузки страницы (3 секунды)...")
        sys.stdout.flush()
        time.sleep(3)
        
        # Проверяем текущий URL
        print("Проверяем текущий URL...")
        sys.stdout.flush()
        try:
            current_url = driver.current_url
            print(f"✓ Текущий URL: {current_url}")
            sys.stdout.flush()
            
            if current_url == "data:," or current_url.startswith("chrome://"):
                print("⚠ Браузер открыт, но не перешел на сайт!")
                print("Попытка повторной навигации...")
                sys.stdout.flush()
                driver.get(MAIN_PAGE_URL)
                time.sleep(3)
                current_url = driver.current_url
                print(f"Новый URL: {current_url}")
                sys.stdout.flush()
            
            if current_url != MAIN_PAGE_URL and "login" in current_url.lower():
                print("⚠ Похоже, требуется авторизация. Проверьте, что вы вошли в систему.")
                sys.stdout.flush()
        except Exception as url_error:
            print(f"⚠ Не удалось получить текущий URL: {url_error}")
            sys.stdout.flush()
        
    except Exception as nav_error:
        print(f"✗ ОШИБКА при навигации: {nav_error}")
        import traceback
        traceback.print_exc()
        sys.stdout.flush()
        print("\nПопытка продолжить работу...")
    
    try:
        print("Ищем список заданий...")
        sys.stdout.flush()
        lessons_list = find_lessons_list(driver)
        
        if not lessons_list:
            print("⚠ Не удалось найти список заданий!")
            print(f"Текущий URL: {driver.current_url}")
            print("Текущий заголовок страницы:", driver.title)
            print("\nВозможные причины:")
            print("1. Страница еще не загрузилась - попробуйте увеличить время ожидания")
            print("2. Вы не авторизованы на сайте")
            print("3. Структура страницы изменилась")
            print("\nСкрипт продолжит работу, но может не найти задания.")
            # Не выходим, продолжаем работу
        
        print("Извлекаем ссылки на задания...")
        task_links = get_task_links(driver, lessons_list)
        
        print(f"Найдено заданий: {len(task_links)}")
        
        # Выводим информацию о заданиях
        for i, task in enumerate(task_links, 1):
            status = "✓ Выполнено" if task["completed"] else "✗ Не выполнено"
            print(f"{i}. {task['href']} - {status}")
        
        # Проходим по каждому заданию
        for i, task in enumerate(task_links, 1):
            print(f"\n[{i}/{len(task_links)}] Переходим к заданию: {task['href']}")
            
            # Переходим на страницу задания
            driver.get(task['href'])
            
            # Ждем загрузки страницы
            time.sleep(2)
            
            print(f"  На странице задания. URL: {driver.current_url}")
            
            # Возвращаемся на главную страницу
            print("  Возвращаемся на главную страницу...")
            driver.get(MAIN_PAGE_URL)
            time.sleep(2)
            
            # Обновляем список заданий после возврата
            lessons_list = find_lessons_list(driver)
            if lessons_list:
                task_links = get_task_links(driver, lessons_list)
        
        print("\n✓ Все задания обработаны!")
        
    except Exception as e:
        print(f"Произошла ошибка: {e}")
        import traceback
        traceback.print_exc()
    
    finally:
        if driver:
            print("\nЗакрываем браузер...")
            time.sleep(2)
            try:
                driver.quit()
            except:
                pass

if __name__ == "__main__":
    main()

