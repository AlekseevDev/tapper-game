import os
import json
import logging
from telegram import Update, WebAppInfo, InlineKeyboardButton, InlineKeyboardMarkup, ChatMember
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes, CallbackQueryHandler
from dotenv import load_dotenv
import time

# Загрузка переменных окружения
load_dotenv()

# Настройка логирования
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)

# Константы
BOT_TOKEN = "7480394291:AAFm2nXc685V7MR5ZiuXklk3LpXz8YtkqwA"
WEBAPP_URL = "https://alekseevdev.github.io/tapper-game/"
APP_VERSION = "2.1.0"

# Хранение данных пользователей
user_data = {}
leaderboard = {}

# Скины и их условия
SKINS = {
    'default': {'name': 'Стандартный', 'requirement': 0},
    'bronze': {'name': 'Бронзовый', 'requirement': 100},
    'silver': {'name': 'Серебряный', 'requirement': 500},
    'gold': {'name': 'Золотой', 'requirement': 1000}
}

# Достижения
ACHIEVEMENTS = [
    {'id': 'first100', 'name': '100 тапов', 'requirement': 100},
    {'id': 'first500', 'name': '500 тапов', 'requirement': 500},
    {'id': 'first1000', 'name': '1000 тапов', 'requirement': 1000}
]

def init_user_data(user_id, username):
    """Инициализация данных пользователя"""
    if user_id not in user_data:
        user_data[user_id] = {
            'username': username,
            'total_taps': 0,
            'best_score': 0,
            'current_skin': 'default',
            'unlocked_skins': ['default'],
            'achievements': [],
            'app_version': None  # Добавляем отслеживание версии приложения
        }

def check_achievements(user_id):
    """Проверка достижений пользователя"""
    user = user_data[user_id]
    new_achievements = []
    
    for achievement in ACHIEVEMENTS:
        if (achievement['id'] not in user['achievements'] and 
            user['total_taps'] >= achievement['requirement']):
            user['achievements'].append(achievement['id'])
            new_achievements.append(achievement['name'])
    
    return new_achievements

def check_skins(user_id):
    """Проверка доступных скинов"""
    user = user_data[user_id]
    new_skins = []
    
    for skin_id, skin_data in SKINS.items():
        if (skin_id not in user['unlocked_skins'] and 
            user['total_taps'] >= skin_data['requirement']):
            user['unlocked_skins'].append(skin_id)
            new_skins.append(skin_data['name'])
    
    return new_skins

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработчик команды /start"""
    user_id = update.effective_user.id
    username = update.effective_user.username or "Игрок"
    
    # Инициализация данных пользователя
    init_user_data(user_id, username)
    user = user_data[user_id]
    
    # Проверяем версию приложения
    if user['app_version'] != APP_VERSION:
        user['app_version'] = APP_VERSION
        webapp_url = f"{WEBAPP_URL}?v={APP_VERSION}"  # Добавляем версию в URL
    else:
        webapp_url = WEBAPP_URL
    
    keyboard = [[
        InlineKeyboardButton(
            "🎮 Начать игру",
            web_app=WebAppInfo(url=webapp_url)
        )
    ]]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await update.message.reply_text(
        "🎮 Добро пожаловать в игру Тапалка!\n\n"
        "Нажми кнопку ниже, чтобы начать игру:",
        reply_markup=reply_markup
    )

async def check_subscription(bot, user_id, channel_username):
    """Проверка подписки пользователя на канал"""
    try:
        chat_member = await bot.get_chat_member(chat_id=channel_username, user_id=user_id)
        return chat_member.status in ['member', 'administrator', 'creator']
    except Exception as e:
        logging.error(f"Error checking subscription: {e}")
        return False

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработчик текстовых сообщений"""
    # Пустая функция, так как админ-консоль удалена
    pass

async def handle_webapp_data(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработчик данных от веб-приложения"""
    try:
        data = json.loads(update.effective_message.web_app_data.data)
        user_id = update.effective_user.id
        username = update.effective_user.username or "Игрок"
        
        # Инициализация данных пользователя
        init_user_data(user_id, username)
        user = user_data[user_id]
        
        if data['action'] == 'gameEnd':
            score = data['score']
            total_taps = data.get('totalTaps', score)
            
            # Обновляем статистику
            user['total_taps'] = total_taps
            if score > user['best_score']:
                user['best_score'] = score
            
            # Проверяем новые достижения и скины
            new_achievements = check_achievements(user_id)
            new_skins = check_skins(user_id)
            
            # Обновляем таблицу лидеров
            leaderboard[user_id] = {
                'username': username,
                'best_score': user['best_score']
            }
            
            # Формируем сообщение с результатами
            message = f"🎯 Твой результат: {score} тапов\n"
            
            if score > user['best_score']:
                message += "🏆 Новый рекорд!\n\n"
            
            if new_achievements:
                message += "🎉 Новые достижения:\n"
                for achievement in new_achievements:
                    message += f"✨ {achievement}\n"
                message += "\n"
            
            if new_skins:
                message += "🎨 Новые скины:\n"
                for skin in new_skins:
                    message += f"🎁 {skin}\n"
            
            # Добавляем кнопку для новой игры
            keyboard = [[
                InlineKeyboardButton(
                    "🎮 Играть снова",
                    web_app=WebAppInfo(url=WEBAPP_URL)
                )
            ]]
            reply_markup = InlineKeyboardMarkup(keyboard)
            
            await update.effective_message.reply_text(
                message,
                reply_markup=reply_markup
            )
        elif data['action'] == 'checkSubscription':
            channel = data.get('channel')
            if channel:
                is_subscribed = await check_subscription(context.bot, user_id, channel)
                await update.effective_message.reply_text(
                    json.dumps({'subscribed': is_subscribed})
                )
            
    except Exception as e:
        logging.error(f"Ошибка при обработке данных веб-приложения: {e}")
        await update.effective_message.reply_text(
            "Произошла ошибка при обработке данных."
        )

def main():
    """Запуск бота"""
    application = Application.builder().token(BOT_TOKEN).build()
    
    # Обработчики команд
    application.add_handler(CommandHandler("start", start))
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    application.add_handler(MessageHandler(filters.StatusUpdate.WEB_APP_DATA, handle_webapp_data))
    
    # Запуск бота
    application.run_polling(allowed_updates=Update.ALL_TYPES)

if __name__ == '__main__':
    main() 