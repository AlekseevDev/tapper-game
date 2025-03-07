import sqlite3
from datetime import datetime, timedelta
import os

class Database:
    def __init__(self, db_file):
        self.db_file = db_file
        self.init_db()

    def init_db(self):
        """Инициализация базы данных"""
        conn = sqlite3.connect(self.db_file)
        c = conn.cursor()

        try:
            c.execute('BEGIN TRANSACTION')

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

            # Создаем индекс для быстрой сортировки
            c.execute('''CREATE INDEX IF NOT EXISTS idx_taps_per_minute 
                        ON players(taps_per_minute DESC)''')

            # Создаем таблицу истории результатов
            c.execute('''CREATE TABLE IF NOT EXISTS score_history
                        (id INTEGER PRIMARY KEY AUTOINCREMENT,
                         user_id INTEGER NOT NULL,
                         score INTEGER NOT NULL,
                         timestamp TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
                         FOREIGN KEY(user_id) REFERENCES players(user_id))''')

            # Создаем таблицу выполненных заданий
            c.execute('''CREATE TABLE IF NOT EXISTS completed_tasks
                        (id INTEGER PRIMARY KEY AUTOINCREMENT,
                         user_id INTEGER NOT NULL,
                         task_id TEXT NOT NULL,
                         completed_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
                         FOREIGN KEY(user_id) REFERENCES players(user_id))''')

            # Создаем уникальный индекс для предотвращения дублирования заданий
            c.execute('''CREATE UNIQUE INDEX IF NOT EXISTS idx_user_task 
                        ON completed_tasks(user_id, task_id)''')

            conn.commit()

        except Exception as e:
            conn.rollback()
            raise e

        finally:
            conn.close()

    def get_player(self, user_id):
        """Получение данных игрока"""
        conn = sqlite3.connect(self.db_file)
        c = conn.cursor()

        try:
            c.execute('SELECT * FROM players WHERE user_id = ?', (user_id,))
            player = c.fetchone()

            if player:
                return {
                    'user_id': player[0],
                    'nickname': player[1],
                    'avatar': player[2],
                    'total_taps': player[3],
                    'best_score': player[4],
                    'tap_power': player[5],
                    'taps_per_minute': player[6],
                    'last_updated': player[7]
                }

            # Если игрок не найден, создаем нового
            new_player = {
                'user_id': user_id,
                'nickname': 'Игрок',
                'avatar': 'avatar1',
                'total_taps': 0,
                'best_score': 0,
                'tap_power': 1,
                'taps_per_minute': 0
            }
            self.update_player(user_id, new_player)
            return new_player

        finally:
            conn.close()

    def update_player(self, user_id, data):
        """Обновление данных игрока"""
        conn = sqlite3.connect(self.db_file)
        c = conn.cursor()

        try:
            c.execute('BEGIN TRANSACTION')

            # Получаем текущие данные игрока
            c.execute('SELECT * FROM players WHERE user_id = ?', (user_id,))
            current_player = c.fetchone()

            if current_player:
                # Обновляем существующего игрока
                c.execute('''UPDATE players SET 
                            nickname = COALESCE(?, nickname),
                            avatar = COALESCE(?, avatar),
                            total_taps = COALESCE(?, total_taps),
                            best_score = COALESCE(?, best_score),
                            tap_power = COALESCE(?, tap_power),
                            taps_per_minute = COALESCE(?, taps_per_minute),
                            last_updated = CURRENT_TIMESTAMP
                            WHERE user_id = ?''',
                         (data.get('nickname'), data.get('avatar'),
                          data.get('total_taps'), data.get('best_score'),
                          data.get('tap_power'), data.get('taps_per_minute'),
                          user_id))
            else:
                # Создаем нового игрока
                c.execute('''INSERT INTO players 
                            (user_id, nickname, avatar, total_taps, best_score, tap_power, taps_per_minute)
                            VALUES (?, ?, ?, ?, ?, ?, ?)''',
                         (user_id,
                          data.get('nickname', 'Игрок'),
                          data.get('avatar', 'avatar1'),
                          data.get('total_taps', 0),
                          data.get('best_score', 0),
                          data.get('tap_power', 1),
                          data.get('taps_per_minute', 0)))

            # Записываем историю счета
            if 'score' in data:
                c.execute('''INSERT INTO score_history (user_id, score)
                            VALUES (?, ?)''', (user_id, data['score']))

            conn.commit()

        except Exception as e:
            conn.rollback()
            raise e

        finally:
            conn.close()

    def get_leaderboard(self, limit=500):
        """Получение таблицы лидеров"""
        conn = sqlite3.connect(self.db_file)
        c = conn.cursor()

        try:
            c.execute('''SELECT user_id, nickname, avatar, taps_per_minute 
                        FROM players 
                        WHERE taps_per_minute > 0 
                        ORDER BY taps_per_minute DESC 
                        LIMIT ?''', (limit,))
            
            return [{
                'user_id': row[0],
                'nickname': row[1],
                'avatar': row[2],
                'tapsPerMinute': row[3]
            } for row in c.fetchall()]

        finally:
            conn.close()

    def complete_task(self, user_id, task_id):
        """Отметка о выполнении задания"""
        conn = sqlite3.connect(self.db_file)
        c = conn.cursor()

        try:
            c.execute('''INSERT OR IGNORE INTO completed_tasks (user_id, task_id)
                        VALUES (?, ?)''', (user_id, task_id))
            conn.commit()
            return c.rowcount > 0

        finally:
            conn.close()

    def get_completed_tasks(self, user_id):
        """Получение списка выполненных заданий"""
        conn = sqlite3.connect(self.db_file)
        c = conn.cursor()

        try:
            c.execute('SELECT task_id FROM completed_tasks WHERE user_id = ?', (user_id,))
            return [row[0] for row in c.fetchall()]

        finally:
            conn.close()

    def cleanup_old_records(self, days=30):
        """Очистка старых записей"""
        conn = sqlite3.connect(self.db_file)
        c = conn.cursor()

        try:
            c.execute('BEGIN TRANSACTION')
            
            # Очищаем старые записи из истории
            c.execute('''DELETE FROM score_history 
                        WHERE timestamp < datetime('now', '-? days')''', (days,))

            # Очищаем записи неактивных игроков
            c.execute('''DELETE FROM players 
                        WHERE last_updated < datetime('now', '-? days')
                        AND total_taps = 0''', (days,))

            conn.commit()

        except Exception as e:
            conn.rollback()
            raise e

        finally:
            conn.close()