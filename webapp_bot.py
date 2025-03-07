import os
import json
import logging
import asyncio
from telegram import Update, WebAppInfo, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes
from dotenv import load_dotenv
import time
from database import Database

# Загрузка переменных окружения
load_dotenv()

# Настройка логирования
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)

logger = logging.getLogger(__name__)

# Константы
APP_VERSION = "2.4.0"

# Инициализация базы данных
db = Database('game.db')

async def cleanup_task(context: ContextTypes.DEFAULT_TYPE):
    """Периодическая очистка старых записей"""
    try:
        db.cleanup_old_records()
        logger.info("Очистка старых записей выполнена успешно")
    except Exception as e:
        logger.error(f"Ошибка при очистке старых записей: {e}")

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработчик команды /start"""
    keyboard = [[InlineKeyboardButton(
        "Играть", 
        web_app=WebAppInfo(url=f"https://alekseevdev.github.io/tapper-game/?v={APP_VERSION}&t={int(time.time())}")
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
            # Отправляем админ-консоль
            keyboard = [[InlineKeyboardButton(
                "Открыть админ-консоль", 
                web_app=WebAppInfo(url=f"https://alekseevdev.github.io/tapper-game/admin.html?v={APP_VERSION}&t={int(time.time())}")
            )]]
            reply_markup = InlineKeyboardMarkup(keyboard)
            await update.message.reply_text("Админ-консоль:", reply_markup=reply_markup)
        else:
            await update.message.reply_text("У вас нет прав администратора.")

async def handle_webapp_data(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработчик данных от веб-приложения"""
    try:
        data = json.loads(update.effective_message.web_app_data.data)
        user_id = update.effective_user.id
        
        if data.get('action') == 'gameEnd':
            # Получаем текущие данные игрока
            current_player = db.get_player(user_id)
            if not current_player:
                current_player = {
                    'total_taps': 0,
                    'best_score': 0,
                    'tap_power': 1,
                    'taps_per_minute': 0,
                    'nickname': 'Игрок',
                    'avatar': 'avatar1'
                }
            
            # Обновляем данные игрока
            score = data.get('score', 0)
            new_total_taps = current_player['total_taps'] + score
            new_best_score = max(current_player['best_score'], score)
            
            player_data = {
                'nickname': data.get('nickname', current_player['nickname']),
                'avatar': data.get('avatar', current_player['avatar']),
                'total_taps': new_total_taps,
                'best_score': new_best_score,
                'tap_power': data.get('tapPower', current_player['tap_power']),
                'taps_per_minute': data.get('tapsPerMinute', current_player['taps_per_minute']),
                'score': score
            }
            
            # Обновляем данные в базе
            db.update_player(user_id, player_data)
            
            # Формируем сообщение с результатами
            message = (
                f"🎮 Игра завершена!\n"
                f"📊 Результат: {score} тапов\n"
                f"⚡ Тапов в минуту: {player_data['taps_per_minute']}\n"
                f"🏆 Всего тапов: {new_total_taps}"
            )
            
            if score >= new_best_score:
                message += "\n🌟 Новый рекорд!"
            
            await update.message.reply_text(message)

        elif data.get('action') == 'getLeaderboard':
            # Получаем данные таблицы лидеров
            leaderboard = db.get_leaderboard()
            
            # Получаем текущего игрока
            current_player = db.get_player(user_id)
            if current_player:
                # Проверяем, есть ли игрок в списке лидеров
                current_in_list = any(p['user_id'] == user_id for p in leaderboard)
                if not current_in_list:
                    # Добавляем игрока в список
                    leaderboard.append({
                        'user_id': user_id,
                        'nickname': current_player['nickname'],
                        'avatar': current_player['avatar'],
                        'tapsPerMinute': current_player['taps_per_minute']
                    })
                    # Сортируем список по убыванию tapsPerMinute
                    leaderboard.sort(key=lambda x: x['tapsPerMinute'], reverse=True)
            
            await update.message.reply_text(
                json.dumps({
                    'leaderboard': leaderboard,
                    'currentUserId': user_id
                }),
                disable_web_page_preview=True
            )

        elif data.get('action') == 'loadUserData':
            # Загружаем данные пользователя
            player = db.get_player(user_id)
            if player:
                await update.message.reply_text(json.dumps({
                    'status': 'success',
                    'data': player
                }))
            else:
                # Создаем нового игрока
                new_player = {
                    'user_id': user_id,
                    'nickname': 'Игрок',
                    'avatar': 'avatar1',
                    'total_taps': 0,
                    'best_score': 0,
                    'tap_power': 1,
                    'taps_per_minute': 0
                }
                db.update_player(user_id, new_player)
                await update.message.reply_text(json.dumps({
                    'status': 'success',
                    'data': new_player
                }))

        elif data.get('action') == 'checkSubscription':
            # Проверяем подписку на канал
            channel = data.get('channel', '').replace('@', '')
            try:
                member = await context.bot.get_chat_member(f"@{channel}", user_id)
                is_member = member.status in ['member', 'administrator', 'creator']
                if is_member:
                    # Отмечаем выполнение задания
                    db.complete_task(user_id, f"channel_{channel}")
                await update.message.reply_text(json.dumps({'subscribed': is_member}))
            except Exception as e:
                await update.message.reply_text(json.dumps({'subscribed': False, 'error': str(e)}))

        elif data.get('action') == 'adminUpdate':
            # Проверяем права администратора
            if user_id == context.bot_data.get('admin_id'):
                # Обновляем версию приложения
                global APP_VERSION
                APP_VERSION = data.get('version', APP_VERSION)
                await update.message.reply_text("✅ Настройки интерфейса обновлены")
            else:
                await update.message.reply_text("❌ У вас нет прав администратора")

    except Exception as e:
        logger.error(f"Ошибка при обработке данных: {e}")
        await update.message.reply_text(f"❌ Произошла ошибка: {str(e)}")

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