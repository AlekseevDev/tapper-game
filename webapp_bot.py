import os
import json
import logging
import asyncio
from telegram import Update, WebAppInfo, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes
from dotenv import load_dotenv
import time
from database import Database
from webapp_database import WebAppDatabase

# Загрузка переменных окружения
load_dotenv()

# Настройка логирования
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO,
    handlers=[
        logging.FileHandler('bot.log'),
        logging.StreamHandler()
    ]
)

logger = logging.getLogger(__name__)

# Константы
APP_VERSION = "3.4.0"

# Пути к базам данных
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
GAME_DB_PATH = os.path.join(BASE_DIR, 'data', 'game.db')
WEBAPP_DB_PATH = os.path.join(BASE_DIR, 'data', 'webapp.db')

# Создаем директорию для баз данных
os.makedirs(os.path.join(BASE_DIR, 'data'), exist_ok=True)

# Инициализация баз данных
db = Database(GAME_DB_PATH)  # для данных бота
webapp_db = WebAppDatabase(WEBAPP_DB_PATH)  # для данных веб-приложения

async def cleanup_task(context: ContextTypes.DEFAULT_TYPE):
    """Периодическая очистка старых записей"""
    try:
        db.cleanup_old_records()
        logger.info("Очистка старых записей выполнена успешно")
    except Exception as e:
        logger.error(f"Ошибка при очистке старых записей: {e}")

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработчик команды /start"""
    user_id = update.effective_user.id
    user_name = update.effective_user.first_name
    
    # Создаем пользователя в базе данных при первом запуске
    try:
        webapp_db.get_or_create_user(user_id)
    except Exception as e:
        logger.error(f"Error creating user {user_id}: {e}")

    # Формируем URL с минимальными параметрами
    webapp_url = "https://alekseevdev.github.io/tapper-game/"

    keyboard = [[InlineKeyboardButton(
        "Играть", 
        web_app=WebAppInfo(url=webapp_url)
    )]]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await update.message.reply_text(
        "Добро пожаловать в Tapper Game!\nНажимайте кнопку 'Играть', чтобы начать.",
        reply_markup=reply_markup
    )

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработчик входящих сообщений"""
    if update.message.text == "CONSOLEMOD":
        # Проверяем, является ли пользователь администратором
        admin_id = context.bot_data.get('admin_id')
        if not admin_id:
            # Первый, кто отправил CONSOLEMOD, становится админом
            context.bot_data['admin_id'] = update.effective_user.id
            await update.message.reply_text("Вы назначены администратором. Используйте админ-консоль для управления интерфейсом.")
        elif admin_id == update.effective_user.id:
            # Формируем URL для админ-консоли
            admin_url = "https://alekseevdev.github.io/tapper-game/admin.html"
            
            keyboard = [[InlineKeyboardButton(
                "Открыть админ-консоль", 
                web_app=WebAppInfo(url=admin_url)
            )]]
            reply_markup = InlineKeyboardMarkup(keyboard)
            await update.message.reply_text("Админ-консоль:", reply_markup=reply_markup)
        else:
            await update.message.reply_text("У вас нет прав администратора.")

async def handle_webapp_data(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработчик данных от веб-приложения"""
    try:
        # Проверяем, что данные пришли от правильного пользователя
        user_id = update.effective_user.id
        if not user_id:
            logger.error("No user ID in update")
            await update.message.reply_text("Error: Could not identify user")
            return

        # Получаем и проверяем данные
        try:
            data = json.loads(update.effective_message.web_app_data.data)
            logger.info(f"Received webapp data: {data} from user {user_id}")
        except json.JSONDecodeError as e:
            logger.error(f"Invalid JSON data from user {user_id}: {e}")
            await update.message.reply_text("Error: Invalid data format")
            return
        
        if data.get('action') == 'gameEnd':
            # Получаем текущие данные пользователя
            current_data = webapp_db.get_or_create_user(user_id)
            if not current_data:
                logger.error(f"Could not get/create user {user_id}")
                await update.message.reply_text("Error: Could not access user data")
                return

            # Проверяем и нормализуем данные
            score = max(0, int(data.get('score', 0)))
            taps_per_minute = max(0, int(data.get('tapsPerMinute', 0)))
            tap_power = max(1, int(data.get('tapPower', 1)))
            coins_earned = max(0, int(data.get('coinsEarned', score // 10)))
            
            # Подготавливаем обновленные данные с проверкой типов
            update_data = {
                'nickname': str(data.get('nickname', current_data['nickname'])),
                'avatar': str(data.get('avatar', current_data['avatar'])),
                'total_taps': current_data['total_taps'] + score,
                'best_score': max(current_data['best_score'], score),
                'tap_power': tap_power,
                'taps_per_minute': max(current_data['taps_per_minute'], taps_per_minute),
                'coins': current_data['coins'] + coins_earned
            }
            
            try:
                # Обновляем данные в базе с проверкой успешности
                webapp_db.update_user_data(user_id, update_data)
                logger.info(f"Successfully updated data for user {user_id}")
            except Exception as e:
                logger.error(f"Failed to update user data for {user_id}: {e}")
                await update.message.reply_text("Error: Could not save game results")
                return
            
            # Проверяем достижения
            try:
                if score > 1000:
                    webapp_db.record_achievement(current_data['id'], 'high_score', score)
                if taps_per_minute > 100:
                    webapp_db.record_achievement(current_data['id'], 'speed_demon', taps_per_minute)
            except Exception as e:
                logger.error(f"Failed to record achievements for {user_id}: {e}")
            
            # Формируем сообщение с результатами
            message = (
                f"🎮 Игра завершена!\n"
                f"📊 Результат: {score} тапов\n"
                f"⚡ Тапов в минуту: {taps_per_minute}\n"
                f"🏆 Всего тапов: {update_data['total_taps']}\n"
                f"💰 Получено монет: {coins_earned}"
            )
            
            if score >= update_data['best_score']:
                message += "\n🌟 Новый рекорд!"
            
            await update.message.reply_text(message)

        elif data.get('action') == 'getLeaderboard':
            try:
                leaderboard = webapp_db.get_leaderboard()
                response_data = {
                    'status': 'success',
                    'leaderboard': [{
                        'user_id': entry['telegram_id'],
                        'nickname': entry['nickname'],
                        'avatar': entry['avatar'],
                        'totalTaps': entry['total_taps'],
                        'bestScore': entry['best_score'],
                        'tapsPerMinute': entry['taps_per_minute'],
                        'lastActive': entry['last_active']
                    } for entry in leaderboard],
                    'currentUserId': user_id,
                    'total_players': len(leaderboard)
                }
                logger.info(f"Sending leaderboard data: {len(leaderboard)} entries")
                await update.message.reply_text(json.dumps(response_data))
            except Exception as e:
                logger.error(f"Failed to get leaderboard: {e}")
                await update.message.reply_text(json.dumps({
                    'status': 'error',
                    'message': "Could not load leaderboard"
                }))

        elif data.get('action') == 'loadUserData':
            try:
                player = webapp_db.get_or_create_user(user_id)
                if not player:
                    raise ValueError("Could not load user data")
                
                response_data = {
                    'status': 'success',
                    'data': {
                        'user_id': player['telegram_id'],
                        'nickname': player['nickname'],
                        'avatar': player['avatar'],
                        'total_taps': player['total_taps'],
                        'best_score': player['best_score'],
                        'tap_power': player['tap_power'],
                        'taps_per_minute': player['taps_per_minute'],
                        'coins': player['coins']
                    }
                }
                await update.message.reply_text(json.dumps(response_data))
                logger.info(f"Sent user data to client: {response_data}")
            except Exception as e:
                logger.error(f"Failed to load user data for {user_id}: {e}")
                await update.message.reply_text("Error: Could not load user data")

        elif data.get('action') == 'updateProfile':
            try:
                current_data = webapp_db.get_or_create_user(user_id)
                if not current_data:
                    raise ValueError("Could not access user data")
                
                update_data = {
                    'nickname': str(data.get('nickname', current_data['nickname'])),
                    'avatar': str(data.get('avatar', current_data['avatar']))
                }
                webapp_db.update_user_data(user_id, update_data)
                await update.message.reply_text(json.dumps({'status': 'success'}))
            except Exception as e:
                logger.error(f"Failed to update profile for {user_id}: {e}")
                await update.message.reply_text("Error: Could not update profile")

    except Exception as e:
        logger.error(f"Error handling webapp data: {e}")
        await update.message.reply_text(json.dumps({
            'status': 'error',
            'message': str(e)
        }))

def main():
    """Запуск бота"""
    try:
        # Загружаем токен из файла
        with open('token.txt', 'r') as f:
            token = f.read().strip()

        # Создаем приложение
        application = Application.builder().token(token).build()

        # Добавляем обработчики
        application.add_handler(CommandHandler("start", start))
        application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
        application.add_handler(MessageHandler(filters.StatusUpdate.WEB_APP_DATA, handle_webapp_data))

        # Добавляем задачу очистки старых записей (каждые 24 часа)
        application.job_queue.run_repeating(cleanup_task, interval=86400)

        # Запускаем бота
        logger.info("Бот запущен")
        application.run_polling(allowed_updates=Update.ALL_TYPES)

    except Exception as e:
        logger.error(f"Ошибка при запуске бота: {e}")

if __name__ == '__main__':
    main() 