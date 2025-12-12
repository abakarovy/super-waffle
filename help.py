from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.chrome.options import Options
import time
import os
import sys
import subprocess

# URL главной страницы
MAIN_PAGE_URL = "https://kb.cifrium.ru/teacher/courses/771"
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
    
    # Открываем главную страницу
    print(f"\nОткрываем главную страницу: {MAIN_PAGE_URL}")
    driver.get(MAIN_PAGE_URL)
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
    elif MAIN_PAGE_URL in current_url or "teacher/courses" in current_url:
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
        print("1. Убедитесь, что вы на странице: https://kb.cifrium.ru/teacher/courses/771")
        print("2. Нажмите Enter в этом окне")
        print("=" * 50)
        input("\n>>> Нажмите Enter после того, как войдете в систему...")
        
        # Проверяем, залогинились ли
        current_url = driver.current_url
        print(f"\nТекущий URL после входа: {current_url}")
        
        if MAIN_PAGE_URL in current_url or "teacher/courses" in current_url:
            print("✓ Отлично! Вы залогинены и на нужной странице.")
        else:
            print(f"⚠ Текущий URL: {current_url}")
            print("Переходим на целевую страницу...")
            driver.get(MAIN_PAGE_URL)
            time.sleep(3)
            
            final_url = driver.current_url
            if MAIN_PAGE_URL in final_url or "teacher/courses" in final_url:
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
    if MAIN_PAGE_URL in final_url or "teacher/courses" in final_url:
        print("✓ Сайт открыт и вы залогинены!")
    else:
        print(f"⚠ Текущий URL: {final_url}")
    print(f"{'='*50}\n")
    
    # Продолжаем работу со скриптом
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

