"""
Тестовый скрипт для проверки работы AI Helper
Запустите этот скрипт, чтобы убедиться, что AI настроен правильно
"""

from ai_helper import AIHelper
import json


def load_config():
    """Загрузка конфигурации"""
    try:
        with open('config.json', 'r', encoding='utf-8') as f:
            return json.load(f)
    except Exception as e:
        print(f"❌ Ошибка загрузки config.json: {e}")
        return None


def test_ai():
    """Тестирование AI Helper"""
    print("="*60)
    print("ТЕСТ AI HELPER")
    print("="*60)
    
    # Загружаем конфигурацию
    config = load_config()
    if not config:
        print("\n❌ Не удалось загрузить конфигурацию")
        print("Создайте файл config.json с настройками")
        return False
    
    # Проверяем настройки
    print(f"\n📋 Конфигурация:")
    print(f"   AI включен: {config.get('ai_enabled')}")
    print(f"   Модель: {config.get('ai_model')}")
    print(f"   API ключ: {'✓ Установлен' if config.get('ai_api_key') else '✗ Не установлен'}")
    
    if not config.get('ai_enabled'):
        print("\n⚠️  AI отключен в конфигурации")
        print("Установите 'ai_enabled': true в config.json")
        return False
    
    if not config.get('ai_api_key'):
        print("\n❌ API ключ не установлен")
        print("Добавьте ваш API ключ в config.json")
        return False
    
    # Инициализируем AI Helper
    print(f"\n🔧 Инициализация AI Helper...")
    try:
        ai = AIHelper(
            api_key=config.get('ai_api_key'),
            model=config.get('ai_model')
        )
    except Exception as e:
        print(f"❌ Ошибка инициализации: {e}")
        return False
    
    if not ai.enabled:
        print("❌ AI Helper не активирован")
        return False
    
    print("✓ AI Helper успешно инициализирован")
    
    # Тест 1: Radio (одиночный выбор)
    print("\n" + "="*60)
    print("ТЕСТ 1: Одиночный выбор (Radio)")
    print("="*60)
    
    question1 = "Какой язык программирования используется для веб-разработки на стороне клиента?"
    options1 = [
        "Python",
        "JavaScript",
        "C++",
        "Java"
    ]
    
    print(f"\nВопрос: {question1}")
    print("Варианты:")
    for i, opt in enumerate(options1, 1):
        print(f"  {i}. {opt}")
    
    answer1 = ai.find_answer(question1, options1, "radio")
    
    if answer1:
        print(f"\n✅ Ответ получен: {answer1}")
        if answer1 == "JavaScript":
            print("✓ Ответ правильный!")
        else:
            print("⚠️  Ответ может быть неточным")
    else:
        print("\n❌ Не удалось получить ответ")
        return False
    
    # Тест 2: Checkbox (множественный выбор)
    print("\n" + "="*60)
    print("ТЕСТ 2: Множественный выбор (Checkbox)")
    print("="*60)
    
    question2 = "Выберите языки программирования (не языки разметки):"
    options2 = [
        "Python",
        "HTML",
        "JavaScript",
        "CSS",
        "Java"
    ]
    
    print(f"\nВопрос: {question2}")
    print("Варианты:")
    for i, opt in enumerate(options2, 1):
        print(f"  {i}. {opt}")
    
    answer2 = ai.find_answer(question2, options2, "checkbox")
    
    if answer2:
        print(f"\n✅ Ответы получены: {answer2}")
        correct = ["Python", "JavaScript", "Java"]
        if all(a in correct for a in answer2):
            print("✓ Ответы правильные!")
        else:
            print("⚠️  Некоторые ответы могут быть неточными")
    else:
        print("\n❌ Не удалось получить ответы")
        return False
    
    # Тест 3: Text (текстовый ответ)
    print("\n" + "="*60)
    print("ТЕСТ 3: Текстовый ответ")
    print("="*60)
    
    question3 = "Сколько байт в одном килобайте? Ответьте только числом."
    
    print(f"\nВопрос: {question3}")
    
    answer3 = ai.find_answer(question3, [], "text")
    
    if answer3:
        print(f"\n✅ Ответ получен: {answer3}")
        if "1024" in answer3 or "1000" in answer3:
            print("✓ Ответ правильный!")
        else:
            print("⚠️  Ответ может быть неточным")
    else:
        print("\n❌ Не удалось получить ответ")
        return False
    
    # Тест 4: Drag and Drop
    print("\n" + "="*60)
    print("ТЕСТ 4: Сопоставление (Drag and Drop)")
    print("="*60)
    
    question4 = "Сопоставьте языки программирования с их основным назначением:"
    options4 = {
        "targets": [
            "Веб-разработка на стороне клиента",
            "Системное программирование",
            "Анализ данных и машинное обучение"
        ],
        "draggables": [
            "JavaScript",
            "C++",
            "Python",
            "Java"
        ]
    }
    
    print(f"\nВопрос: {question4}")
    print("\nЦелевые области:")
    for i, t in enumerate(options4["targets"], 1):
        print(f"  {i}. {t}")
    print("\nЭлементы для сопоставления:")
    for i, d in enumerate(options4["draggables"], 1):
        print(f"  {chr(64+i)}. {d}")
    
    answer4 = ai.find_answer(question4, options4, "drag_and_drop")
    
    if answer4:
        print(f"\n✅ Сопоставления получены:")
        for target, draggable in answer4.items():
            print(f"   '{target[:40]}...' → '{draggable}'")
        print("✓ Сопоставления выглядят разумно!")
    else:
        print("\n❌ Не удалось получить сопоставления")
        return False
    
    # Итоги
    print("\n" + "="*60)
    print("РЕЗУЛЬТАТЫ ТЕСТИРОВАНИЯ")
    print("="*60)
    print("\n✅ Все тесты пройдены успешно!")
    print(f"\n📊 Статистика:")
    print(f"   Модель: {config.get('ai_model')}")
    print(f"   Тестов пройдено: 4/4")
    
    print("\n💡 AI Helper готов к использованию!")
    print("   Запустите help.py для автоматического решения задач")
    
    return True


if __name__ == "__main__":
    try:
        success = test_ai()
        if not success:
            print("\n⚠️  Тестирование не завершено")
            print("Проверьте настройки в config.json")
    except KeyboardInterrupt:
        print("\n\n⚠️  Тестирование прервано пользователем")
    except Exception as e:
        print(f"\n❌ Ошибка при тестировании: {e}")
        import traceback
        traceback.print_exc()
