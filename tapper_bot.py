import os
import logging
import asyncio
from datetime import datetime, timedelta
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, CallbackQueryHandler, ContextTypes
from dotenv import load_dotenv

# Загрузка переменных окружения
load_dotenv()

# Настройка логирования
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)

# Константы
BOT_TOKEN = "7480394291:AAFm2nXc685V7MR5ZiuXklk3LpXz8YtkqwA"  # Токен бота
GAME_DURATION = 30  # Длительность игры в секундах

# Хранение данных пользователей
user_scores = {}  # Общие очки пользователей
active_games = {}  # Активные игры
leaderboard = {}  # Таблица лидеров

def format_time(seconds):
    """Форматирование времени"""
    return str(timedelta(seconds=seconds)).split('.')[0]

def create_game_keyboard():
    """Создание клавиатуры для игры"""
    keyboard = [
        [InlineKeyboardButton("🎯 ТАП! 🎯", callback_data='tap')],
        [InlineKeyboardButton("🏁 Закончить игру", callback_data='end_game')]
    ]
    return InlineKeyboardMarkup(keyboard)

def create_main_keyboard():
    """Создание главной клавиатуры"""
    keyboard = [
        [InlineKeyboardButton("🎮 Начать игру", callback_data='start_game')],
        [InlineKeyboardButton("🏆 Таблица лидеров", callback_data='leaderboard')],
        [InlineKeyboardButton("ℹ️ Как играть", callback_data='help')]
    ]
    return InlineKeyboardMarkup(keyboard)

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработчик команды /start"""
    user_id = update.effective_user.id
    username = update.effective_user.username or "Игрок"
    
    if user_id not in user_scores:
        user_scores[user_id] = 0
        leaderboard[user_id] = {"username": username, "best_score": 0}
    
    await update.message.reply_text(
        f"🎮 Привет, {username}!\n\n"
        "Добро пожаловать в игру ТАПАЛКА!\n"
        "Тапай как можно быстрее и побей рекорд!\n\n"
        f"🏆 Твой лучший результат: {leaderboard[user_id]['best_score']} тапов",
        reply_markup=create_main_keyboard()
    )

async def game_timer(context: ContextTypes.DEFAULT_TYPE):
    """Таймер игры"""
    job = context.job
    chat_id = job.data['chat_id']
    user_id = job.data['user_id']
    
    if user_id in active_games:
        score = active_games[user_id]['score']
        # Обновляем лучший результат
        if score > leaderboard[user_id]['best_score']:
            leaderboard[user_id]['best_score'] = score
        
        # Добавляем очки к общему счету
        user_scores[user_id] += score
        
        await context.bot.edit_message_text(
            f"🎮 Игра окончена!\n\n"
            f"🎯 Твой результат: {score} тапов\n"
            f"🏆 Лучший результат: {leaderboard[user_id]['best_score']} тапов\n"
            f"💫 Всего очков: {user_scores[user_id]}",
            chat_id=chat_id,
            message_id=active_games[user_id]['message_id'],
            reply_markup=create_main_keyboard()
        )
        del active_games[user_id]

async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработчик нажатий кнопок"""
    query = update.callback_query
    user_id = query.from_user.id
    chat_id = query.message.chat_id
    
    if query.data == 'start_game':
        if user_id in active_games:
            await query.answer("У тебя уже есть активная игра!")
            return
        
        # Создаем новую игру
        active_games[user_id] = {
            'score': 0,
            'start_time': datetime.now(),
            'message_id': query.message.message_id
        }
        
        # Устанавливаем таймер
        context.job_queue.run_once(
            game_timer,
            GAME_DURATION,
            data={'chat_id': chat_id, 'user_id': user_id}
        )
        
        await query.edit_message_text(
            f"🎮 Игра началась!\n"
            f"⏱ Время: {GAME_DURATION} секунд\n"
            f"🎯 Очки: 0",
            reply_markup=create_game_keyboard()
        )
    
    elif query.data == 'tap':
        if user_id not in active_games:
            await query.answer("Игра не активна! Начни новую игру.")
            return
        
        game = active_games[user_id]
        game['score'] += 1
        
        time_left = GAME_DURATION - (datetime.now() - game['start_time']).seconds
        if time_left < 0:
            time_left = 0
        
        await query.answer()
        await query.edit_message_text(
            f"🎮 Тапай быстрее!\n"
            f"⏱ Осталось: {time_left} сек\n"
            f"🎯 Очки: {game['score']}",
            reply_markup=create_game_keyboard()
        )
    
    elif query.data == 'end_game':
        if user_id in active_games:
            # Отменяем таймер
            for job in context.job_queue.get_jobs_by_name(str(user_id)):
                job.schedule_removal()
            
            # Вызываем завершение игры
            await game_timer(context._context)
        await query.answer("Игра завершена!")
    
    elif query.data == 'leaderboard':
        # Сортируем таблицу лидеров
        sorted_leaders = sorted(
            leaderboard.items(),
            key=lambda x: x[1]['best_score'],
            reverse=True
        )[:10]
        
        leaderboard_text = "🏆 Таблица лидеров:\n\n"
        for i, (_, data) in enumerate(sorted_leaders, 1):
            leaderboard_text += f"{i}. {data['username']}: {data['best_score']} тапов\n"
        
        await query.edit_message_text(
            leaderboard_text,
            reply_markup=create_main_keyboard()
        )
    
    elif query.data == 'help':
        await query.edit_message_text(
            "🎮 Как играть в ТАПАЛКУ:\n\n"
            "1. Нажми 'Начать игру'\n"
            "2. У тебя есть 30 секунд\n"
            "3. Тапай по кнопке '🎯 ТАП! 🎯' как можно быстрее\n"
            "4. Побей свой рекорд и стань лучшим в таблице лидеров!\n\n"
            "Удачи! 🍀",
            reply_markup=create_main_keyboard()
        )

def main():
    """Запуск бота"""
    # Создаем приложение с поддержкой очереди задач
    application = Application.builder().token(BOT_TOKEN).build()
    
    # Добавляем обработчики
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CallbackQueryHandler(button_handler))
    
    # Запускаем бота
    application.run_polling(allowed_updates=Update.ALL_TYPES)

if __name__ == '__main__':
    main() 