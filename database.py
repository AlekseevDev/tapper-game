import sqlite3
import os
import logging
from datetime import datetime
import threading

logger = logging.getLogger(__name__)

class Database:
    _instance = None
    _lock = threading.Lock()
    
    def __new__(cls, db_file):
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    cls._instance = super(Database, cls).__new__(cls)
                    cls._instance.db_file = db_file
                    cls._instance.init_db()
        return cls._instance

    def __init__(self, db_file):
        self.db_file = db_file
        self._local = threading.local()

    def get_connection(self):
        """Получение соединения для текущего потока"""
        if not hasattr(self._local, 'connection'):
            self._local.connection = sqlite3.connect(self.db_file, check_same_thread=False)
            self._local.connection.row_factory = sqlite3.Row
            self._local.connection.execute('PRAGMA foreign_keys = ON')
        return self._local.connection

    def init_db(self):
        """Инициализация базы данных"""
        os.makedirs(os.path.dirname(os.path.abspath(self.db_file)), exist_ok=True)
        
        conn = sqlite3.connect(self.db_file)
        c = conn.cursor()

        try:
            # Таблица игроков с игровыми данными
            c.execute('''CREATE TABLE IF NOT EXISTS players
                        (user_id INTEGER PRIMARY KEY,
                         nickname TEXT NOT NULL DEFAULT 'Игрок',
                         avatar TEXT NOT NULL DEFAULT 'avatar1',
                         total_taps INTEGER NOT NULL DEFAULT 0,
                         best_score INTEGER NOT NULL DEFAULT 0,
                         tap_power INTEGER NOT NULL DEFAULT 1,
                         taps_per_minute INTEGER NOT NULL DEFAULT 0,
                         current_score INTEGER NOT NULL DEFAULT 0,
                         game_state TEXT NOT NULL DEFAULT 'idle',
                         last_tap_time TIMESTAMP,
                         session_start_time TIMESTAMP,
                         last_updated TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP)''')

            # Таблица игровых сессий
            c.execute('''CREATE TABLE IF NOT EXISTS game_sessions
                        (id INTEGER PRIMARY KEY AUTOINCREMENT,
                         user_id INTEGER NOT NULL,
                         start_time TIMESTAMP NOT NULL,
                         end_time TIMESTAMP,
                         total_taps INTEGER NOT NULL DEFAULT 0,
                         score INTEGER NOT NULL DEFAULT 0,
                         taps_per_minute INTEGER NOT NULL DEFAULT 0,
                         FOREIGN KEY(user_id) REFERENCES players(user_id) ON DELETE CASCADE)''')

            # Таблица истории тапов
            c.execute('''CREATE TABLE IF NOT EXISTS tap_history
                        (id INTEGER PRIMARY KEY AUTOINCREMENT,
                         user_id INTEGER NOT NULL,
                         session_id INTEGER NOT NULL,
                         tap_time TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
                         tap_power INTEGER NOT NULL DEFAULT 1,
                         FOREIGN KEY(user_id) REFERENCES players(user_id) ON DELETE CASCADE,
                         FOREIGN KEY(session_id) REFERENCES game_sessions(id) ON DELETE CASCADE)''')

            # Индексы для оптимизации
            c.execute('CREATE INDEX IF NOT EXISTS idx_game_sessions_user ON game_sessions(user_id)')
            c.execute('CREATE INDEX IF NOT EXISTS idx_tap_history_session ON tap_history(session_id)')
            c.execute('CREATE INDEX IF NOT EXISTS idx_player_score ON players(taps_per_minute DESC, total_taps DESC)')

            conn.commit()
            logger.info("Game database initialized successfully")

        except Exception as e:
            conn.rollback()
            logger.error(f"Game database initialization error: {e}")
            raise
        finally:
            conn.close()

    def start_game_session(self, user_id):
        """Начало новой игровой сессии"""
        conn = self.get_connection()
        c = conn.cursor()

        try:
            # Создаем или обновляем игрока
            c.execute('''INSERT OR REPLACE INTO players 
                        (user_id, game_state, current_score, session_start_time, last_updated)
                        VALUES (?, 'playing', 0, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)
                        ON CONFLICT(user_id) DO UPDATE SET
                        game_state='playing',
                        current_score=0,
                        session_start_time=CURRENT_TIMESTAMP,
                        last_updated=CURRENT_TIMESTAMP''', (user_id,))

            # Создаем новую игровую сессию
            c.execute('''INSERT INTO game_sessions (user_id, start_time)
                        VALUES (?, CURRENT_TIMESTAMP)''', (user_id,))
            
            session_id = c.lastrowid
            conn.commit()
            logger.info(f"Started new game session {session_id} for user {user_id}")
            return session_id

        except Exception as e:
            conn.rollback()
            logger.error(f"Error starting game session: {e}")
            raise

    def record_tap(self, user_id, session_id, tap_power=1):
        """Запись тапа в текущей сессии"""
        conn = self.get_connection()
        c = conn.cursor()

        try:
            # Записываем тап
            c.execute('''INSERT INTO tap_history (user_id, session_id, tap_power)
                        VALUES (?, ?, ?)''', (user_id, session_id, tap_power))

            # Обновляем текущий счет и время последнего тапа
            c.execute('''UPDATE players SET 
                        current_score = current_score + ?,
                        last_tap_time = CURRENT_TIMESTAMP,
                        last_updated = CURRENT_TIMESTAMP
                        WHERE user_id = ?''', (tap_power, user_id))

            # Обновляем статистику сессии
            c.execute('''UPDATE game_sessions SET
                        total_taps = total_taps + 1,
                        score = score + ?
                        WHERE id = ?''', (tap_power, session_id))

            conn.commit()
            logger.info(f"Recorded tap for user {user_id} in session {session_id}")

        except Exception as e:
            conn.rollback()
            logger.error(f"Error recording tap: {e}")
            raise

    def end_game_session(self, user_id, session_id):
        """Завершение игровой сессии"""
        conn = self.get_connection()
        c = conn.cursor()

        try:
            # Получаем данные сессии
            c.execute('''SELECT total_taps, score, 
                        (julianday(CURRENT_TIMESTAMP) - julianday(start_time)) * 24 * 60 as duration
                        FROM game_sessions WHERE id = ?''', (session_id,))
            session = c.fetchone()

            if session:
                duration_minutes = float(session['duration'])
                taps_per_minute = int(session['total_taps'] / duration_minutes) if duration_minutes > 0 else 0

                # Обновляем статистику сессии
                c.execute('''UPDATE game_sessions SET
                            end_time = CURRENT_TIMESTAMP,
                            taps_per_minute = ?
                            WHERE id = ?''', (taps_per_minute, session_id))

                # Обновляем общую статистику игрока
                c.execute('''UPDATE players SET
                            total_taps = total_taps + ?,
                            best_score = CASE WHEN ? > best_score THEN ? ELSE best_score END,
                            taps_per_minute = CASE WHEN ? > taps_per_minute THEN ? ELSE taps_per_minute END,
                            game_state = 'idle',
                            current_score = 0,
                            last_updated = CURRENT_TIMESTAMP
                            WHERE user_id = ?''',
                         (session['total_taps'], session['score'], session['score'],
                          taps_per_minute, taps_per_minute, user_id))

                conn.commit()
                logger.info(f"Ended game session {session_id} for user {user_id}")
                return {
                    'total_taps': session['total_taps'],
                    'score': session['score'],
                    'taps_per_minute': taps_per_minute
                }

        except Exception as e:
            conn.rollback()
            logger.error(f"Error ending game session: {e}")
            raise

    def get_player(self, user_id):
        """Получение данных игрока"""
        conn = self.get_connection()
        c = conn.cursor()

        try:
            c.execute('''SELECT * FROM players WHERE user_id = ?''', (user_id,))
            player = c.fetchone()

            if not player:
                # Создаем нового игрока
                c.execute('''INSERT INTO players (user_id) VALUES (?)''', (user_id,))
                conn.commit()
                c.execute('''SELECT * FROM players WHERE user_id = ?''', (user_id,))
                player = c.fetchone()

            return dict(player)

        except Exception as e:
            logger.error(f"Error getting player data: {e}")
            raise

    def get_leaderboard(self, limit=500):
        """Получение таблицы лидеров"""
        conn = self.get_connection()
        c = conn.cursor()

        try:
            c.execute('''SELECT user_id, nickname, avatar, taps_per_minute, total_taps
                        FROM players
                        WHERE taps_per_minute > 0 OR total_taps > 0
                        ORDER BY taps_per_minute DESC, total_taps DESC
                        LIMIT ?''', (limit,))
            
            return [dict(row) for row in c.fetchall()]

        except Exception as e:
            logger.error(f"Error getting leaderboard: {e}")
            raise

    def cleanup_old_records(self, days=30):
        """Очистка старых записей"""
        conn = self.get_connection()
        c = conn.cursor()

        try:
            # Удаляем старые сессии и связанные записи
            c.execute('''DELETE FROM game_sessions 
                        WHERE start_time < datetime('now', '-? days')''', (days,))

            # Очищаем неактивных игроков
            c.execute('''DELETE FROM players 
                        WHERE last_updated < datetime('now', '-? days')
                        AND total_taps = 0 
                        AND taps_per_minute = 0''', (days,))

            conn.commit()
            logger.info(f"Cleaned up old records older than {days} days")

        except Exception as e:
            conn.rollback()
            logger.error(f"Error cleaning up old records: {e}")
            raise

class WebAppDatabase:
    _instance = None
    _lock = threading.Lock()
    
    def __new__(cls, db_file):
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    cls._instance = super(WebAppDatabase, cls).__new__(cls)
                    cls._instance.db_file = db_file
                    cls._instance.init_db()
        return cls._instance

    def __init__(self, db_file):
        self.db_file = db_file
        self._local = threading.local()

    def get_connection(self):
        if not hasattr(self._local, 'connection'):
            self._local.connection = sqlite3.connect(self.db_file, check_same_thread=False)
            self._local.connection.row_factory = sqlite3.Row
        return self._local.connection

    def init_db(self):
        os.makedirs(os.path.dirname(os.path.abspath(self.db_file)), exist_ok=True)
        
        conn = sqlite3.connect(self.db_file)
        c = conn.cursor()

        try:
            # Таблица пользователей веб-приложения
            c.execute('''CREATE TABLE IF NOT EXISTS webapp_users
                        (id INTEGER PRIMARY KEY AUTOINCREMENT,
                         telegram_id INTEGER UNIQUE,
                         nickname TEXT NOT NULL DEFAULT 'Игрок',
                         avatar TEXT NOT NULL DEFAULT 'avatar1',
                         total_taps INTEGER NOT NULL DEFAULT 0,
                         best_score INTEGER NOT NULL DEFAULT 0,
                         tap_power INTEGER NOT NULL DEFAULT 1,
                         taps_per_minute INTEGER NOT NULL DEFAULT 0,
                         coins INTEGER NOT NULL DEFAULT 0,
                         last_updated TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP)''')

            # Таблица достижений
            c.execute('''CREATE TABLE IF NOT EXISTS achievements
                        (id INTEGER PRIMARY KEY AUTOINCREMENT,
                         user_id INTEGER NOT NULL,
                         achievement_type TEXT NOT NULL,
                         value INTEGER NOT NULL DEFAULT 0,
                         unlocked_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
                         FOREIGN KEY(user_id) REFERENCES webapp_users(id) ON DELETE CASCADE)''')

            # Таблица покупок
            c.execute('''CREATE TABLE IF NOT EXISTS purchases
                        (id INTEGER PRIMARY KEY AUTOINCREMENT,
                         user_id INTEGER NOT NULL,
                         item_type TEXT NOT NULL,
                         item_id TEXT NOT NULL,
                         cost INTEGER NOT NULL,
                         purchased_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
                         FOREIGN KEY(user_id) REFERENCES webapp_users(id) ON DELETE CASCADE)''')

            # Индексы
            c.execute('CREATE INDEX IF NOT EXISTS idx_webapp_users_score ON webapp_users(taps_per_minute DESC, total_taps DESC)')
            c.execute('CREATE INDEX IF NOT EXISTS idx_achievements_user ON achievements(user_id)')
            c.execute('CREATE INDEX IF NOT EXISTS idx_purchases_user ON purchases(user_id)')

            conn.commit()
            logger.info("Web app database initialized successfully")

        except Exception as e:
            conn.rollback()
            logger.error(f"Web app database initialization error: {e}")
            raise
        finally:
            conn.close()

    def get_or_create_user(self, telegram_id):
        """Получение или создание пользователя веб-приложения"""
        conn = self.get_connection()
        c = conn.cursor()

        try:
            # Пытаемся найти пользователя
            c.execute('SELECT * FROM webapp_users WHERE telegram_id = ?', (telegram_id,))
            user = c.fetchone()

            if not user:
                # Создаем нового пользователя
                c.execute('''INSERT INTO webapp_users (telegram_id) VALUES (?)''', (telegram_id,))
                conn.commit()
                
                c.execute('SELECT * FROM webapp_users WHERE telegram_id = ?', (telegram_id,))
                user = c.fetchone()

            return dict(user)

        except Exception as e:
            conn.rollback()
            logger.error(f"Error getting/creating web app user: {e}")
            raise

    def update_user_data(self, telegram_id, data):
        """Обновление данных пользователя"""
        conn = self.get_connection()
        c = conn.cursor()

        try:
            # Получаем текущие данные пользователя
            current_data = self.get_or_create_user(telegram_id)
            
            # Подготавливаем данные для обновления
            update_data = {
                'nickname': str(data.get('nickname', current_data['nickname'])),
                'avatar': str(data.get('avatar', current_data['avatar'])),
                'total_taps': max(0, int(data.get('total_taps', current_data['total_taps']))),
                'best_score': max(0, int(data.get('best_score', current_data['best_score']))),
                'tap_power': max(1, int(data.get('tap_power', current_data['tap_power']))),
                'taps_per_minute': max(0, int(data.get('taps_per_minute', current_data['taps_per_minute']))),
                'coins': max(0, int(data.get('coins', current_data['coins'])))
            }

            # Обновляем данные пользователя
            c.execute('''UPDATE webapp_users SET 
                        nickname = :nickname,
                        avatar = :avatar,
                        total_taps = :total_taps,
                        best_score = :best_score,
                        tap_power = :tap_power,
                        taps_per_minute = :taps_per_minute,
                        coins = :coins,
                        last_updated = CURRENT_TIMESTAMP
                        WHERE telegram_id = :telegram_id''',
                     {**update_data, 'telegram_id': telegram_id})

            conn.commit()
            logger.info(f"Updated web app user data: {update_data}")
            return update_data

        except Exception as e:
            conn.rollback()
            logger.error(f"Error updating web app user data: {e}")
            raise

    def get_leaderboard(self, limit=500):
        """Получение таблицы лидеров"""
        conn = self.get_connection()
        c = conn.cursor()

        try:
            c.execute('''SELECT telegram_id, nickname, avatar, taps_per_minute, total_taps
                        FROM webapp_users
                        WHERE taps_per_minute > 0 OR total_taps > 0
                        ORDER BY taps_per_minute DESC, total_taps DESC
                        LIMIT ?''', (limit,))
            
            return [dict(row) for row in c.fetchall()]

        except Exception as e:
            logger.error(f"Error getting web app leaderboard: {e}")
            raise

    def record_achievement(self, user_id, achievement_type, value):
        """Запись достижения пользователя"""
        conn = self.get_connection()
        c = conn.cursor()

        try:
            c.execute('''INSERT INTO achievements (user_id, achievement_type, value)
                        VALUES (?, ?, ?)''', (user_id, achievement_type, value))
            conn.commit()
            logger.info(f"Recorded achievement for user {user_id}: {achievement_type} = {value}")

        except Exception as e:
            conn.rollback()
            logger.error(f"Error recording achievement: {e}")
            raise

    def record_purchase(self, user_id, item_type, item_id, cost):
        """Запись покупки пользователя"""
        conn = self.get_connection()
        c = conn.cursor()

        try:
            # Проверяем баланс пользователя
            c.execute('SELECT coins FROM webapp_users WHERE id = ?', (user_id,))
            user = c.fetchone()
            
            if user and user['coins'] >= cost:
                # Записываем покупку
                c.execute('''INSERT INTO purchases (user_id, item_type, item_id, cost)
                            VALUES (?, ?, ?, ?)''', (user_id, item_type, item_id, cost))
                
                # Обновляем баланс
                c.execute('''UPDATE webapp_users SET 
                            coins = coins - ?,
                            last_updated = CURRENT_TIMESTAMP
                            WHERE id = ?''', (cost, user_id))
                
                conn.commit()
                logger.info(f"Recorded purchase for user {user_id}: {item_type} {item_id} for {cost} coins")
                return True
            return False

        except Exception as e:
            conn.rollback()
            logger.error(f"Error recording purchase: {e}")
            raise

# Создаем экземпляр базы данных веб-приложения
webapp_db = WebAppDatabase('webapp.db')