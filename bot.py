import asyncio
import logging
from datetime import datetime
import os
import re
from aiogram import Bot, Dispatcher, types
from aiogram.filters import Command
from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup
from aiogram.exceptions import TelegramForbiddenError
from dotenv import load_dotenv

# Загружаем переменные из файла .env
load_dotenv()
TOKEN = os.getenv("BOT_TOKEN")

# Настройка логирования
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')

# Инициализация бота и диспетчера
bot = Bot(token=TOKEN)
dp = Dispatcher()

# Хранилище данных пользователей (в оперативной памяти)
# Структура: {user_id: {
#   "active": bool, 
#   "training": bool,
#   "schedules": [{"day": int, "hour": int, "minute": int}],
#   "last_reminder_date": str (YYYY-MM-DD)
# }}
users = {}

# Словари для парсинга дней недели
DAYS_MAP = {
    "пн": 0, "понедельник": 0, "mon": 0,
    "вт": 1, "вторник": 1, "tue": 1,
    "ср": 2, "среда": 2, "wed": 2,
    "чт": 3, "четверг": 3, "thu": 3,
    "пт": 4, "пятница": 4, "fri": 4,
    "сб": 5, "суббота": 5, "sat": 5,
    "вс": 6, "воскресенье": 6, "sun": 6
}

# Функция для проверки, является ли текущий день запланированным
def is_scheduled_day(days_list):
    now = datetime.now()
    current_day = now.weekday() # Понедельник - 0, Воскресенье - 6
    return current_day in days_list

# Функция для проверки, наступило ли время тренировки
def is_training_time(schedule):
    now = datetime.now()
    if now.hour > schedule["hour"]:
        return True # Время уже прошло сегодня (или мы в режиме ожидания)
    if now.hour == schedule["hour"] and now.minute >= schedule["minute"]:
        return True
    return False

# Функция для отправки напоминания всем активным пользователям
async def reminder_loop():
    while True:
        await asyncio.sleep(60)  # Пауза 60 секунд
        now = datetime.now()
        today_str = now.strftime("%Y-%m-%d")

        for user_id, data in users.items():
            if not data["active"]:
                continue
            
            # Если пользователь уже тренируется сегодня — пропускаем
            if data["training"] and data.get("last_reminder_date") == today_str:
                continue

            schedules = data.get("schedules", [])
            for sched in schedules:
                days_list = sched.get("days", [])
                # Проверяем, подходит ли сегодня под расписание
                if days_list and is_scheduled_day(days_list):
                    # Если наступило время тренировки (или оно уже прошло сегодня)
                    if is_training_time(sched):
                        # Если мы еще не пометили этот день как "тренировка началась"
                        if data.get("last_reminder_date") != today_str:
                            try:
                                await bot.send_message(
                                    user_id, 
                                    f"⏰ Пора тренироваться! (Запланировано на {sched['hour']}:{sched['minute']})"
                                )
                                # Мы не ставим last_reminder_date здесь, так как мы хотим напоминать каждую минуту
                                # пока он не нажмет кнопку. Но нам нужно знать, что это "сегодняшний" цикл.
                            except TelegramForbiddenError:
                                logging.warning(f"Пользователь {user_id} заблокировал бота.")
                            except Exception as e:
                                logging.error(f"Ошибка при отправке напоминания пользователю {user_id}: {e}")

# Обработчик команды /start
@dp.message(Command("start"))
async def cmd_start(message: types.Message):
    user_id = message.from_user.id
    if user_id not in users:
        users[user_id] = {
            "active": False, 
            "training": False,
            "schedules": [],
            "last_reminder_date": ""
        }
    
    await message.answer(
        "Привет! Я твой умный бот-напоминалка.\n\n"
        "Просто напиши мне свои тренировки в свободном стиле, например:\n"
        "• Понедельник 17:00\n"
        "• Четверг и Суббота 18:30\n\n"
        "Команды:\n"
        "/status — проверить текущий статус и расписание\n"
        "/stop — выключить всё"
    )

# Обработчик команды /stop
@dp.message(Command("stop"))
async def cmd_stop(message: types.Message):
    user_id = message.from_user.id
    if user_id in users:
        users[user_id]["active"] = False
        users[user_id]["training"] = False
        await message.answer("🛑 Режим напоминаний выключен.")

# Обработчик команды /status
@dp.message(Command("status"))
async def cmd_status(message: types.Message):
    user_id = message.from_user.id
    if user_id in users:
        data = users[user_id]
        schedules = data.get("schedules", [])
        
        if not schedules:
            sched_info = "Не задано"
        else:
            res = []
            for s in schedules:
                days_names = [k for k, v in DAYS_MAP.items() if v == s['day']]
                res.append(f"{', '.join(days_names)} {s['hour']}:{s['minute']}")
            sched_info = " • ".join(res)

        status = "Включен" if data["active"] else "Выключен"
        training = "Идет тренировка" if data["training"] else "Тренировка не начата"
        
        await message.answer(
            f"Ваш статус:\nРежим: {status}\nСостояние: {training}\n\n"
            f"Расписание:\n{sched_info}"
        )
    else:
        await message.answer("Вы еще не активировали бота.")

# Обработчик всех остальных сообщений (умный парсинг без команд)
@dp.message()
async def handle_natural_language(message: types.Message):
    user_id = message.from_user.id
    if user_id not in users:
        users[user_id] = {"active": False, "training": False, "schedules": [], "last_reminder_date": ""}

    text = message.text
    # Ищем дни недели и время в тексте сообщения
    new_schedules = []
    parts = re.split(r',|и|или', text) # Разделяем по запятой или союзам
    
    found_any = False
    for part in parts:
        part = part.strip()
        if not part: continue
        
        day_found = None
        # Проверяем наличие дня недели в строке (регистронезависимо)
        lower_part = part.lower()
        for day_name, day_num in DAYS_MAP.items():
            if day_name in lower_part:
                day_found = day_num
                break
        
        # Ищем время в строке (ЧЧ:ММ) с учетом возможных пробелов вокруг двоеточия
        time_match = re.search(r'(\d{1,2})\s*:\s*(\d{2})', part)
        if day_found and time_match:
            hour = int(time_match.group(1))
            minute = int(time_match.group(2))
            new_schedules.append({
                "day": day_found,
                "hour": hour,
                "minute": minute
            })
            found_any = True

    if found_any:
        users[user_id]["schedules"] = new_schedules
        res = []
        for s in new_schedules:
            days_names = [k for k, v in DAYS_MAP.items() if v == s['day']]
            res.append(f"{', '.join(days_names)} {s['hour']}:{s['minute']}")
        await message.answer(f"✅ Запомнил! Расписание обновлено:\n• {' • '.join(res)}")
    else:
        # Если сообщение не содержит расписания, но это не команда, даем подсказку
        if len(text) > 2: # Игнорируем слишком короткие сообщения типа "ок" или "привет"
            await message.answer("Я не совсем понял ваше расписание. Попробуйте написать так: 'Понедельник 17:00' или 'Пн 09:30'.")

# Обработчик нажатия кнопки "Приступил к тренировке"
@dp.callback_query(lambda c: c.data == "start_training")
async def process_start_training(callback: types.CallbackQuery):
    user_id = callback.from_user.id
    if user_id in users:
        users[user_id]["training"] = True
        # Запоминаем дату, чтобы знать, что тренировка прошла именно сегодня
        users[user_id]["last_reminder_date"] = datetime.now().strftime("%Y-%m-%d")
        await callback.message.edit_text("💪 Отлично! Тренировка началась. Напоминания приостановлены.")

# Функция запуска бота
async def main():
    # Запускаем фоновую задачу напоминаний
    asyncio.create_task(reminder_loop())
    
    print("Бот запущен и готов к работе...")
    await dp.start_polling(bot)

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("Бот выключен.")
