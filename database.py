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
            # Создаем таблицу игроков
            c.execute('''CREATE TABLE IF NOT EXISTS players
                        (user_id INTEGER PRIMARY KEY,
                         nickname TEXT NOT NULL DEFAULT 'Игрок',
                         avatar TEXT NOT NULL DEFAULT 'avatar1',
                         total_taps INTEGER NOT NULL DEFAULT 0,
                         best_score INTEGER NOT NULL DEFAULT 0,
                         tap_power INTEGER NOT NULL DEFAULT 1,
                         taps_per_minute INTEGER NOT NULL DEFAULT 0,
                         last_updated TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP)''')

            # Создаем таблицу истории результатов
            c.execute('''CREATE TABLE IF NOT EXISTS score_history
                        (id INTEGER PRIMARY KEY AUTOINCREMENT,
                         user_id INTEGER NOT NULL,
                         score INTEGER NOT NULL,
                         timestamp TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
                         FOREIGN KEY(user_id) REFERENCES players(user_id) ON DELETE CASCADE)''')

            # Создаем таблицу выполненных заданий
            c.execute('''CREATE TABLE IF NOT EXISTS completed_tasks
                        (id INTEGER PRIMARY KEY AUTOINCREMENT,
                         user_id INTEGER NOT NULL,
                         task_id TEXT NOT NULL,
                         completed_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
                         FOREIGN KEY(user_id) REFERENCES players(user_id) ON DELETE CASCADE)''')

            # Создаем индексы
            c.execute('CREATE INDEX IF NOT EXISTS idx_taps_per_minute ON players(taps_per_minute DESC)')
            c.execute('CREATE UNIQUE INDEX IF NOT EXISTS idx_user_task ON completed_tasks(user_id, task_id)')
            c.execute('CREATE INDEX IF NOT EXISTS idx_score_history_user ON score_history(user_id)')

            conn.commit()
            logger.info("Database initialized successfully")

        except Exception as e:
            conn.rollback()
            logger.error(f"Database initialization error: {e}")
            raise
        finally:
            conn.close()

    def get_player(self, user_id):
        """Получение данных игрока"""
        conn = self.get_connection()
        c = conn.cursor()

        try:
            # Проверяем существование игрока
            c.execute('SELECT * FROM players WHERE user_id = ?', (user_id,))
            player = c.fetchone()

            if not player:
                # Создаем нового игрока
                c.execute('''INSERT INTO players 
                           (user_id, nickname, avatar, total_taps, best_score, tap_power, taps_per_minute)
                           VALUES (?, ?, ?, ?, ?, ?, ?)''',
                        (user_id, 'Игрок', 'avatar1', 0, 0, 1, 0))
                conn.commit()
                
                # Получаем созданного игрока
                c.execute('SELECT * FROM players WHERE user_id = ?', (user_id,))
                player = c.fetchone()

            # Формируем данные игрока
            player_data = {
                'user_id': user_id,
                'nickname': player['nickname'],
                'avatar': player['avatar'],
                'total_taps': player['total_taps'],
                'best_score': player['best_score'],
                'tap_power': player['tap_power'],
                'taps_per_minute': player['taps_per_minute'],
                'last_updated': player['last_updated']
            }
            
            logger.info(f"Retrieved player data: {player_data}")
            return player_data

        except Exception as e:
            conn.rollback()
            logger.error(f"Error getting player data: {e}")
            raise

    def update_player(self, user_id, data):
        """Обновление данных игрока"""
        conn = self.get_connection()
        c = conn.cursor()

        try:
            # Получаем текущие данные игрока
            current_data = self.get_player(user_id)
            
            # Подготавливаем данные для обновления
            update_data = {
                'nickname': str(data.get('nickname', current_data['nickname'])),
                'avatar': str(data.get('avatar', current_data['avatar'])),
                'total_taps': max(0, int(data.get('total_taps', current_data['total_taps']))),
                'best_score': max(0, int(data.get('best_score', current_data['best_score']))),
                'tap_power': max(1, int(data.get('tap_power', current_data['tap_power']))),
                'taps_per_minute': max(0, int(data.get('taps_per_minute', current_data['taps_per_minute'])))
            }

            # Обновляем данные игрока
            c.execute('''UPDATE players SET 
                        nickname = :nickname,
                        avatar = :avatar,
                        total_taps = :total_taps,
                        best_score = :best_score,
                        tap_power = :tap_power,
                        taps_per_minute = :taps_per_minute,
                        last_updated = CURRENT_TIMESTAMP
                        WHERE user_id = :user_id''',
                     {**update_data, 'user_id': user_id})

            # Если есть новый счет, добавляем его в историю
            if 'score' in data and int(data['score']) > 0:
                c.execute('''INSERT INTO score_history (user_id, score)
                           VALUES (?, ?)''', (user_id, int(data['score'])))

            conn.commit()
            logger.info(f"Updated player data: {update_data}")

        except Exception as e:
            conn.rollback()
            logger.error(f"Error updating player data: {e}")
            raise

    def get_leaderboard(self, limit=500):
        """Получение таблицы лидеров"""
        conn = self.get_connection()
        c = conn.cursor()

        try:
            # Получаем список лидеров
            c.execute('''SELECT user_id, nickname, avatar, taps_per_minute, total_taps 
                        FROM players 
                        WHERE taps_per_minute > 0 OR total_taps > 0
                        ORDER BY taps_per_minute DESC, total_taps DESC
                        LIMIT ?''', (limit,))
            
            leaderboard = [{
                'user_id': row['user_id'],
                'nickname': row['nickname'],
                'avatar': row['avatar'],
                'tapsPerMinute': row['taps_per_minute'],
                'totalTaps': row['total_taps']
            } for row in c.fetchall()]
            
            logger.info(f"Retrieved leaderboard with {len(leaderboard)} entries")
            return leaderboard

        except Exception as e:
            logger.error(f"Error getting leaderboard: {e}")
            raise

    def complete_task(self, user_id, task_id):
        """Отметка о выполнении задания"""
        conn = self.get_connection()
        c = conn.cursor()

        try:
            c.execute('''INSERT OR IGNORE INTO completed_tasks (user_id, task_id)
                        VALUES (?, ?)''', (user_id, task_id))
            conn.commit()
            success = c.rowcount > 0
            if success:
                logger.info(f"Task {task_id} completed for user {user_id}")
            return success

        except Exception as e:
            conn.rollback()
            logger.error(f"Error completing task: {e}")
            raise

    def get_completed_tasks(self, user_id):
        """Получение списка выполненных заданий"""
        conn = self.get_connection()
        c = conn.cursor()

        try:
            c.execute('SELECT task_id FROM completed_tasks WHERE user_id = ?', (user_id,))
            tasks = [row[0] for row in c.fetchall()]
            logger.info(f"Retrieved {len(tasks)} completed tasks for user {user_id}")
            return tasks

        except Exception as e:
            logger.error(f"Error getting completed tasks: {e}")
            raise

    def cleanup_old_records(self, days=30):
        """Очистка старых записей"""
        conn = self.get_connection()
        c = conn.cursor()

        try:
            # Очищаем старые записи
            c.execute('''DELETE FROM score_history 
                        WHERE timestamp < datetime('now', '-? days')''', (days,))
            
            # Очищаем записи неактивных игроков с нулевыми показателями
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