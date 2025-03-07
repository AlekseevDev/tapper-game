import sqlite3
from datetime import datetime, timedelta
import os
import logging

logger = logging.getLogger(__name__)

class Database:
    def __init__(self, db_file):
        self.db_file = db_file
        self.init_db()
        logger.info(f"Database initialized: {db_file}")

    def init_db(self):
        """Инициализация базы данных"""
        conn = sqlite3.connect(self.db_file)
        c = conn.cursor()

        try:
            c.execute('BEGIN TRANSACTION')

            # Создаем таблицу игроков с обязательными полями
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
                         FOREIGN KEY(user_id) REFERENCES players(user_id) ON DELETE CASCADE)''')

            # Создаем таблицу выполненных заданий
            c.execute('''CREATE TABLE IF NOT EXISTS completed_tasks
                        (id INTEGER PRIMARY KEY AUTOINCREMENT,
                         user_id INTEGER NOT NULL,
                         task_id TEXT NOT NULL,
                         completed_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
                         FOREIGN KEY(user_id) REFERENCES players(user_id) ON DELETE CASCADE)''')

            # Создаем уникальный индекс для предотвращения дублирования заданий
            c.execute('''CREATE UNIQUE INDEX IF NOT EXISTS idx_user_task 
                        ON completed_tasks(user_id, task_id)''')

            conn.commit()
            logger.info("Database tables and indexes created successfully")

        except Exception as e:
            conn.rollback()
            logger.error(f"Error initializing database: {e}")
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
                player_data = {
                    'user_id': player[0],
                    'nickname': player[1],
                    'avatar': player[2],
                    'total_taps': player[3],
                    'best_score': player[4],
                    'tap_power': player[5],
                    'taps_per_minute': player[6],
                    'last_updated': player[7]
                }
                logger.info(f"Retrieved player data: {player_data}")
                return player_data

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
            logger.info(f"Created new player: {new_player}")
            return new_player

        except Exception as e:
            logger.error(f"Error getting player data: {e}")
            raise e

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
                # Обновляем существующего игрока, сохраняя текущие значения если новые не предоставлены
                update_data = {
                    'nickname': data.get('nickname', current_player[1]),
                    'avatar': data.get('avatar', current_player[2]),
                    'total_taps': data.get('total_taps', current_player[3]),
                    'best_score': data.get('best_score', current_player[4]),
                    'tap_power': data.get('tap_power', current_player[5]),
                    'taps_per_minute': data.get('taps_per_minute', current_player[6])
                }
                
                c.execute('''UPDATE players SET 
                            nickname = ?,
                            avatar = ?,
                            total_taps = ?,
                            best_score = ?,
                            tap_power = ?,
                            taps_per_minute = ?,
                            last_updated = CURRENT_TIMESTAMP
                            WHERE user_id = ?''',
                         (update_data['nickname'],
                          update_data['avatar'],
                          update_data['total_taps'],
                          update_data['best_score'],
                          update_data['tap_power'],
                          update_data['taps_per_minute'],
                          user_id))
                logger.info(f"Updated player data: {update_data}")
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
                logger.info(f"Created new player: {data}")

            # Записываем историю счета
            if 'score' in data and data['score'] > 0:
                c.execute('''INSERT INTO score_history (user_id, score)
                            VALUES (?, ?)''', (user_id, data['score']))
                logger.info(f"Recorded score: {data['score']} for user {user_id}")

            conn.commit()

        except Exception as e:
            conn.rollback()
            logger.error(f"Error updating player data: {e}")
            raise e

        finally:
            conn.close()

    def get_leaderboard(self, limit=500):
        """Получение таблицы лидеров"""
        conn = sqlite3.connect(self.db_file)
        c = conn.cursor()

        try:
            c.execute('''SELECT user_id, nickname, avatar, taps_per_minute, total_taps 
                        FROM players 
                        WHERE taps_per_minute > 0 OR total_taps > 0
                        ORDER BY taps_per_minute DESC, total_taps DESC
                        LIMIT ?''', (limit,))
            
            leaderboard = [{
                'user_id': row[0],
                'nickname': row[1],
                'avatar': row[2],
                'tapsPerMinute': row[3],
                'totalTaps': row[4]
            } for row in c.fetchall()]
            
            logger.info(f"Retrieved leaderboard with {len(leaderboard)} entries")
            return leaderboard

        except Exception as e:
            logger.error(f"Error getting leaderboard: {e}")
            raise e

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
            success = c.rowcount > 0
            if success:
                logger.info(f"Task {task_id} completed for user {user_id}")
            return success

        except Exception as e:
            logger.error(f"Error completing task: {e}")
            raise e

        finally:
            conn.close()

    def get_completed_tasks(self, user_id):
        """Получение списка выполненных заданий"""
        conn = sqlite3.connect(self.db_file)
        c = conn.cursor()

        try:
            c.execute('SELECT task_id FROM completed_tasks WHERE user_id = ?', (user_id,))
            tasks = [row[0] for row in c.fetchall()]
            logger.info(f"Retrieved {len(tasks)} completed tasks for user {user_id}")
            return tasks

        except Exception as e:
            logger.error(f"Error getting completed tasks: {e}")
            raise e

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
            logger.info(f"Cleaned up old records older than {days} days")

        except Exception as e:
            conn.rollback()
            logger.error(f"Error cleaning up old records: {e}")
            raise e

        finally:
            conn.close()