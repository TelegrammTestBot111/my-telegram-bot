import asyncio
import logging
import os
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
# Структура: {user_id: {"active": bool, "training": bool}}
users = {}

# Функция для отправки напоминания всем активным пользователям
async def reminder_loop():
    while True:
        await asyncio.sleep(60)  # Пауза 60 секунд
        for user_id, data in users.items():
            if data["active"] and not data["training"]:
                try:
                    await bot.send_message(
                        user_id, 
                        "⏰ Пора тренироваться! Не отвлекайся!"
                    )
                except TelegramForbiddenError:
                    logging.warning(f"Пользователь {user_id} заблокировал бота.")
                except Exception as e:
                    logging.error(f"Ошибка при отправке напоминания пользователю {user_id}: {e}")

# Обработчик команды /start
@dp.message(Command("start"))
async def cmd_start(message: types.Message):
    user_id = message.from_user.id
    if user_id not in users:
        users[user_id] = {"active": False, "training": False}
    
    await message.answer(
        "Привет! Я твой бот-напоминалка.\n\n"
        "Используй команды:\n"
        "/activate — включить напоминания каждую минуту\n"
        "/stop — выключить всё\n"
        "/status — проверить текущий статус"
    )

# Обработчик команды /activate
@dp.message(Command("activate"))
async def cmd_activate(message: types.Message):
    user_id = message.from_user.id
    if user_id not in users:
        users[user_id] = {"active": False, "training": False}
    
    users[user_id]["active"] = True
    users[user_id]["training"] = False
    await message.answer("✅ Режим напоминаний включен! Я буду писать тебе каждую минуту.")

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
        status = "Включен" if data["active"] else "Выключен"
        training = "Идет тренировка" if data["training"] else "Тренировка не начата"
        await message.answer(f"Ваш статус:\nРежим: {status}\nСостояние: {training}")
    else:
        await message.answer("Вы еще не активировали бота.")

# Обработчик нажатия кнопки "Приступил к тренировке"
@dp.callback_query(lambda c: c.data == "start_training")
async def process_start_training(callback: types.CallbackQuery):
    user_id = callback.from_user.id
    if user_id in users:
        users[user_id]["training"] = True
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
