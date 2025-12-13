"""
AI Helper для автоматического поиска ответов на вопросы
Использует OpenRouter API для доступа к DeepSeek и другим моделям
"""

import json
import re
from typing import Dict, List, Optional, Union
import time


class AIHelper:
    """Класс для работы с OpenRouter API (DeepSeek и другие модели)"""
    
    def __init__(self, api_key: Optional[str] = None, model: Optional[str] = None):
        """
        Инициализация AI Helper
        
        Args:
            api_key: API ключ от OpenRouter (получить на https://openrouter.ai/keys)
            model: Название модели (по умолчанию: "deepseek/deepseek-chat")
        """
        self.api_key = api_key
        self.model = model or "deepseek/deepseek-chat"
        self.enabled = api_key is not None
        
        if self.enabled:
            self._init_client()
    
    def _init_client(self):
        """Инициализация OpenRouter клиента"""
        try:
            import openai
            # OpenRouter использует OpenAI-совместимый API
            self.client = openai.OpenAI(
                api_key=self.api_key,
                base_url="https://openrouter.ai/api/v1"
            )
            print(f"✓ OpenRouter API инициализирован")
            print(f"  Модель: {self.model}")
        except ImportError:
            print("⚠ Установите библиотеку: pip install openai")
            self.enabled = False
        except Exception as e:
            print(f"⚠ Ошибка инициализации OpenRouter: {e}")
            self.enabled = False
    
    def find_answer(self, question: str, options: List[str], task_type: str = "radio") -> Union[str, List[str], Dict]:
        """
        Поиск ответа на вопрос с использованием AI
        
        Args:
            question: Текст вопроса
            options: Список вариантов ответа
            task_type: Тип задачи (radio, checkbox, drag_and_drop, code, text)
        
        Returns:
            Ответ в формате, соответствующем типу задачи
        """
        if not self.enabled:
            print("⚠ AI Helper не активирован (нет API ключа)")
            return None
        
        print(f"\n🤖 AI ищет ответ на вопрос...")
        print(f"   Тип: {task_type}")
        print(f"   Вопрос: {question[:100]}...")
        
        try:
            if task_type == "radio":
                return self._find_single_choice(question, options)
            elif task_type == "checkbox":
                return self._find_multiple_choice(question, options)
            elif task_type == "drag_and_drop":
                return self._find_drag_and_drop(question, options)
            elif task_type == "code":
                return self._find_code_answer(question)
            elif task_type == "text":
                return self._find_text_answer(question)
            else:
                print(f"⚠ Неизвестный тип задачи: {task_type}")
                return None
        
        except Exception as e:
            print(f"⚠ Ошибка при поиске ответа: {e}")
            return None
    
    def _find_single_choice(self, question: str, options: List[str]) -> Optional[str]:
        """Поиск ответа для radio (одиночный выбор)"""
        prompt = f"""Вопрос: {question}

Варианты ответа:
{chr(10).join([f"{i+1}. {opt}" for i, opt in enumerate(options)])}

Выбери ОДИН правильный ответ. Ответь ТОЛЬКО номером варианта (1, 2, 3 и т.д.) без дополнительных объяснений."""

        response = self._call_ai(prompt)
        
        if response:
            # Извлекаем номер из ответа
            match = re.search(r'\d+', response)
            if match:
                index = int(match.group()) - 1
                if 0 <= index < len(options):
                    print(f"   ✓ AI выбрал вариант {index + 1}: {options[index][:50]}...")
                    return options[index]
        
        print(f"   ⚠ AI не смог определить ответ")
        return None
    
    def _find_multiple_choice(self, question: str, options: List[str]) -> Optional[List[str]]:
        """Поиск ответов для checkbox (множественный выбор)"""
        prompt = f"""Вопрос: {question}

Варианты ответа:
{chr(10).join([f"{i+1}. {opt}" for i, opt in enumerate(options)])}

Выбери ВСЕ правильные ответы. Ответь ТОЛЬКО номерами вариантов через запятую (например: 1,3,5) без дополнительных объяснений."""

        response = self._call_ai(prompt)
        
        if response:
            # Извлекаем номера из ответа
            numbers = re.findall(r'\d+', response)
            selected = []
            for num in numbers:
                index = int(num) - 1
                if 0 <= index < len(options):
                    selected.append(options[index])
            
            if selected:
                print(f"   ✓ AI выбрал {len(selected)} вариантов")
                return selected
        
        print(f"   ⚠ AI не смог определить ответы")
        return None
    
    def _find_drag_and_drop(self, question: str, options: Dict) -> Optional[Dict]:
        """Поиск сопоставлений для drag and drop"""
        targets = options.get("targets", [])
        draggables = options.get("draggables", [])
        
        prompt = f"""Задание: {question}

Целевые области (куда перетаскивать):
{chr(10).join([f"{i+1}. {t}" for i, t in enumerate(targets)])}

Элементы для перетаскивания:
{chr(10).join([f"{chr(65+i)}. {d}" for i, d in enumerate(draggables)])}

Сопоставь каждую целевую область с соответствующим элементом.
Ответь в формате JSON: {{"номер_цели": "буква_элемента", ...}}
Например: {{"1": "A", "2": "C", "3": "B"}}"""

        response = self._call_ai(prompt)
        
        if response:
            try:
                # Пытаемся извлечь JSON из ответа
                json_match = re.search(r'\{[^}]+\}', response)
                if json_match:
                    mapping = json.loads(json_match.group())
                    
                    # Преобразуем в формат {target_text: draggable_text}
                    result = {}
                    for target_num, draggable_letter in mapping.items():
                        target_idx = int(target_num) - 1
                        draggable_idx = ord(draggable_letter.upper()) - 65
                        
                        if 0 <= target_idx < len(targets) and 0 <= draggable_idx < len(draggables):
                            result[targets[target_idx]] = draggables[draggable_idx]
                    
                    if result:
                        print(f"   ✓ AI создал {len(result)} сопоставлений")
                        return result
            except Exception as e:
                print(f"   ⚠ Ошибка парсинга ответа: {e}")
        
        print(f"   ⚠ AI не смог создать сопоставления")
        return None
    
    def _find_code_answer(self, question: str) -> Optional[str]:
        """Поиск кода для задачи программирования"""
        prompt = f"""Задание по программированию: {question}

Напиши ТОЛЬКО код на Python без дополнительных объяснений. Код должен быть готов к выполнению."""

        response = self._call_ai(prompt)
        
        if response:
            # Извлекаем код из markdown блока, если есть
            code_match = re.search(r'```(?:python)?\n(.*?)\n```', response, re.DOTALL)
            if code_match:
                code = code_match.group(1)
            else:
                code = response
            
            print(f"   ✓ AI сгенерировал код ({len(code)} символов)")
            return code.strip()
        
        print(f"   ⚠ AI не смог сгенерировать код")
        return None
    
    def _find_text_answer(self, question: str) -> Optional[str]:
        """Поиск текстового ответа"""
        prompt = f"""Вопрос: {question}

Дай краткий точный ответ (число, слово или короткую фразу) без дополнительных объяснений."""

        response = self._call_ai(prompt)
        
        if response:
            answer = response.strip()
            print(f"   ✓ AI дал ответ: {answer}")
            return answer
        
        print(f"   ⚠ AI не смог дать ответ")
        return None
    
    def _call_ai(self, prompt: str) -> Optional[str]:
        """Вызов OpenRouter API"""
        try:
            response = self.client.chat.completions.create(
                model=self.model,
                messages=[
                    {"role": "system", "content": "Ты помощник для решения образовательных тестов. Отвечай кратко и точно."},
                    {"role": "user", "content": prompt}
                ],
                temperature=0.3,
                max_tokens=500
            )
            return response.choices[0].message.content.strip()
        except Exception as e:
            print(f"   ⚠ Ошибка вызова OpenRouter API: {e}")
            return None


# Пример использования
if __name__ == "__main__":
    print("="*60)
    print("AI Helper - Тестовый режим")
    print("="*60)
    print("\nДля использования:")
    print("1. Получите API ключ на https://openrouter.ai/keys")
    print("2. Добавьте ключ в config.json")
    print("3. Запустите: python test_ai.py")
    print("\nИли используйте напрямую:")
    print("  helper = AIHelper(api_key='ваш-ключ')")
    print("  answer = helper.find_answer(question, options, 'radio')")
