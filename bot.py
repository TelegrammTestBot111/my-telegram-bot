import asyncio
import logging
from datetime import datetime, timedelta
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
#   "gender": str | None,
#   "schedules": [{"days": [int], "hour": int, "minute": int}], # Повторяющееся
#   "one_time_reminders": [{"text": str, "execute_at": datetime}], # Разовое
#   "last_reminder_date": str (YYYY-MM-DD)
# }}
users = {}

DAYS_MAP = {
    "пн": 0, "понедельник": 0, "mon": 0,
    "вт": 1, "вторник": 1, "tue": 1,
    "ср": 2, "среда": 2, "wed": 2,
    "чт": 3, "четверг": 3, "thu": 3,
    "пт": 4, "пятница": 4, "fri": 4,
    "сб": 5, "суббота": 5, "sat": 5,
    "вс": 6, "воскресенье": 6, "sun": 6
}

def init_user(user_id):
    if user_id not in users:
        users[user_id] = {
            "active": False, 
            "gender": None,
            "schedules": [],
            "one_time_reminders": [],
            "last_reminder_date": ""
        }

# Функция для проверки дня недели
def is_scheduled_day(days_list):
    now = datetime.now()
    return now.weekday() in days_list

# Фоновая задача уведомлений
async def reminder_loop():
    logging.info("Фоновая задача уведомлений запущена.")
    while True:
        await asyncio.sleep(30)  # Проверка каждые 30 секунд для точности
        now = datetime.now()
        today_str = now.strftime("%Y-%m-%d")

        for user_id, data in users.items():
            if not data["active"]:
                continue
            
            # 1. Обработка повторяющегося расписания
            schedules = data.get("schedules", [])
            for sched in schedules:
                days_list = sched.get("days", [])
                if days_list and is_scheduled_day(days_list):
                    # Проверяем, совпадает ли текущее время с расписанием (в пределах минуты)
                    if now.hour == sched["hour"] and now.minute >= sched["minute"]:
                        if data.get("last_reminder_date") != today_str:
                            try:
                                await bot.send_message(
                                    user_id, 
                                    f"⏰ Напоминание по расписанию!\nВремя: {sched['hour']}:{sched['minute']}"
                                )
                                data["last_reminder_date"] = today_str
                            except Exception as e:
                                logging.error(f"Ошибка отправки (расписание): {e}")

            # 2. Обработка разовых напоминаний
            reminders = data.get("one_time_reminders", [])
            for i in range(len(reminders)):
                reminder = reminders[i]
                if now >= reminder["execute_at"]:
                    try:
                        await bot.send_message(user_id, f"🔔 Разовое напоминание:\n{reminder['text']}")
                        # Удаляем выполненное напоминание
                        reminders.pop(i)
                        break # Выходим из цикла после удаления одного элемента
                    except Exception as e:
                        logging.error(f"Ошибка отправки (разовое): {e}")

# Обработчик команды /start
@dp.message(Command("start"))
async def cmd_start(message: types.Message):
    user_id = message.from_user.id
    init_user(user_id)
    
    if users[user_id]["gender"] is None:
        keyboard = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="Я девушка", callback_data="set_gender_female")],
            [InlineKeyboardButton(text="Я парень", callback_data="set_gender_male")]
        ])
        await message.answer("Выберите ваш пол для настройки профиля:", reply_markup=keyboard)
    else:
        await message.answer(
            f"Привет! Я твой универсальный помощник.\n\n"
            f"Ваш пол: {users[user_id]['gender']}\n"
            "Вы можете:\n"
            "1. Написать разовое напоминание (например: 'Позвонить маме через 30 минут')\n"
            "2. Настроить регулярное расписание через команды.\n\n"
            "Команды:\n"
            "/set_schedule — настроить регулярные задачи\n"
            "/status — проверить текущие задачи\n"
            "/clear_schedule — удалить всё расписание\n"
            "/stop — выключить уведомления"
        )

# Обработчик выбора пола
@dp.callback_query(lambda c: c.data.startswith("set_gender_"))
async def callback_set_gender(callback: types.CallbackQuery):
    user_id = callback.from_user.id
    init_user(user_id)

    gender_choice = callback.data.split("_")[2]
    users[user_id]["gender"] = "Девушка" if gender_choice == "female" else "Парень"
    users[user_id]["active"] = True

    await callback.message.edit_text(f"Ваш пол установлен: {users[user_id]['gender']}\n\nТеперь вы можете использовать команды:\n/set_schedule — настроить регулярные задачи\n/status — проверить текущие задачи")

# Обработчик команды /set_schedule
@dp.message(Command("set_schedule"))
async def cmd_set_schedule(message: types.Message):
    user_id = message.from_user.id
    init_user(user_id)

    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="Пн", callback_data="set_day_0"), 
         InlineKeyboardButton(text="Вт", callback_data="set_day_1"),
         InlineKeyboardButton(text="Ср", callback_data="set_day_2")],
        [InlineKeyboardButton(text="Чт", callback_data="set_day_3"),
         InlineKeyboardButton(text="Пт", callback_data="set_day_4"),
         InlineKeyboardButton(text="Сб", callback_data="set_day_5"),
         InlineKeyboardButton(text="Вс", callback_data="set_day_6")]
    ])

    await message.answer("Выберите день недели для регулярной задачи:", reply_markup=keyboard)

# Обработчик нажатия кнопок выбора дня
@dp.callback_query(lambda c: c.data.startswith("set_day_"))
async def callback_set_day(callback: types.CallbackQuery):
    user_id = callback.from_user.id
    init_user(user_id)

    day_num = int(callback.data.split("_")[2])
    users[user_id]["temp_day"] = day_num
    
    day_name = ""
    for name, num in DAYS_MAP.items():
        if num == day_num:
            day_name = name
            break

    await callback.message.edit_text(f"Вы выбрали {day_name.capitalize()}. Теперь напишите время в формате ЧЧ:ММ (например, 18:30).")

# Обработчик команды /stop
@dp.message(Command("stop"))
async def cmd_stop(message: types.Message):
    user_id = message.from_user.id
    if user_id in users:
        users[user_id]["active"] = False
        await message.answer("🛑 Режим уведомлений выключен.")

# Обработчик команды /clear_schedule
@dp.message(Command("clear_schedule"))
async def cmd_clear_schedule(message: types.Message):
    user_id = message.from_user.id
    if user_id in users:
        users[user_id]["schedules"] = []
        await message.answer("🗑 Все регулярные задачи были удалены.")

# Обработчик команды /status
@dp.message(Command("status"))
async def cmd_status(message: types.Message):
    user_id = message.from_user.id
    if user_id in users:
        data = users[user_id]
        
        sched_text = "Не задано"
        if data["schedules"]:
            res = []
            for s in data["schedules"]:
                days_names = [k for k, v in DAYS_MAP.items() if v == s['day']] # Wait, this is still wrong because 'days' is a list now
                # Let me fix it properly here:
                res.append(f"{', '.join([k for k,v in DAYS_MAP.items() if v in s['days']])} {s['hour']}:{s['minute']}")
            sched_text = " • ".join(res)

        reminders_text = ""
        if data["one_time_reminders"]:
            reminders_text = "\n" + "\n".join([f"- {r['text']} (через {r['execute_at']})" for r in data["one_time_reminders"]])

        await message.answer(
            f"📊 Ваш профиль:\n"
            f"Регулярные задачи: {sched_text}\n"
            f"{reminders_text}"
        )
    else:
        await message.answer("Вы еще не активировали бота.")

# Обработчик всех остальных сообщений (Парсинг)
@dp.message()
async def handle_any_message(message: types.Message):
    user_id = message.from_user.id
    init_user(user_id)

    text = message.text
    if not text: return

    # 1. Обработка ввода времени для кнопок (регулярное расписание)
    if users[user_id].get("temp_day") is not None:
        time_match = re.search(r'(\d{1,2})\s*:\s*(\d{2})', text)
        if time_match:
            hour = int(time_match.group(1))
            minute = int(time_match.group(2))
            
            users[user_id]["schedules"].append({
                "days": [users[user_id]["temp_day"]],
                "hour": hour,
                "minute": minute
            })
            
            users[user_id]["temp_day"] = None
            await message.answer(f"✅ Регулярная задача добавлена на {hour}:{minute}")
        else:
            await message.answer("Пожалуйста, введите время в формате ЧЧ:ММ (например, 18:30).")
        return

    # 2. Парсинг разовых напоминаний ("через X минут/часов")
    one_time_match = re.search(r'через\s*(\d+)\s*(минут|часа|часов)', text, re.IGNORECASE)
    if one_time_match:
        amount = int(one_time_match.group(1))
        unit = one_time_match.group(2).lower()
        
        if "мин" in unit:
            delay = timedelta(minutes=amount)
        else:
            delay = timedelta(hours=amount)
            
        execute_at = datetime.now() + delay
        users[user_id]["one_time_reminders"].append({
            "text": text,
            "execute_at": execute_at
        })
        await message.answer(f"✅ Разовое напоминание установлено на {execute_at.strftime('%H:%M:%S')}")
        return

    # 3. Парсинг регулярного расписания из текста (например, "Понедельник 17:00")
    new_schedules = []
    parts = re.split(r',|и|или', text)
    found_any = False
    for part in parts:
        part = part.strip()
        if not part: continue
        day_found = None
        lower_part = part.lower()
        for day_name, day_num in DAYS_MAP.items():
            if day_name in lower_part:
                day_found = day_num
                break
        time_match = re.search(r'(\d{1,2})\s*:\s*(\d{2})', part)
        if day_found and time_match:
            hour = int(time_match.group(1))
            minute = int(time_match.group(2))
            new_schedules.append({
                "days": [day_found],
                "hour": hour,
                "minute": minute
            })
            found_any = True

    if found_any:
        users[user_id]["schedules"] = new_schedules
        await message.answer(f"✅ Регулярное расписание обновлено!")
    else:
        # Если это не команда и не распознано ничего, даем подсказку
        if len(text) > 5:
            await message.answer("Я могу помочь вам:\n1. Создать разовое напоминание (напишите 'через X минут')\n2. Настроить расписание через /set_schedule")

# Функция запуска бота
async def main():
    asyncio.create_task(reminder_loop())
    print("Бот запущен и готов к работе...")
    await dp.start_polling(bot)

if __name__ == "__main__":
    try:
        async.run(main())
    except KeyboardInterrupt:
        print("Бот выключен.")
