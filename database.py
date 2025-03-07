import sqlite3
from datetime import datetime

class Database:
    def __init__(self, db_file):
        self.db_file = db_file
        self.init_db()

    def init_db(self):
        """Инициализация базы данных"""
        conn = sqlite3.connect(self.db_file)
        c = conn.cursor()

        # Создаем таблицу игроков
        c.execute('''CREATE TABLE IF NOT EXISTS players
                    (user_id INTEGER PRIMARY KEY,
                     nickname TEXT,
                     avatar TEXT,
                     total_taps INTEGER DEFAULT 0,
                     best_score INTEGER DEFAULT 0,
                     tap_power INTEGER DEFAULT 1,
                     last_updated TIMESTAMP)''')

        # Создаем таблицу лидеров
        c.execute('''CREATE TABLE IF NOT EXISTS leaderboard
                    (user_id INTEGER,
                     taps_per_minute INTEGER,
                     timestamp TIMESTAMP,
                     FOREIGN KEY(user_id) REFERENCES players(user_id))''')

        # Создаем таблицу выполненных заданий
        c.execute('''CREATE TABLE IF NOT EXISTS completed_tasks
                    (user_id INTEGER,
                     task_id TEXT,
                     completed_at TIMESTAMP,
                     FOREIGN KEY(user_id) REFERENCES players(user_id))''')

        conn.commit()
        conn.close()

    def update_player(self, user_id, data):
        """Обновление данных игрока"""
        conn = sqlite3.connect(self.db_file)
        c = conn.cursor()

        c.execute('''INSERT OR REPLACE INTO players 
                    (user_id, nickname, avatar, total_taps, best_score, tap_power, last_updated)
                    VALUES (?, ?, ?, ?, ?, ?, ?)''',
                 (user_id, data['nickname'], data['avatar'], data['total_taps'],
                  data['best_score'], data.get('tap_power', 1), datetime.now()))

        if 'taps_per_minute' in data:
            c.execute('''INSERT INTO leaderboard (user_id, taps_per_minute, timestamp)
                        VALUES (?, ?, ?)''',
                     (user_id, data['taps_per_minute'], datetime.now()))

        conn.commit()
        conn.close()

    def get_player(self, user_id):
        """Получение данных игрока"""
        conn = sqlite3.connect(self.db_file)
        c = conn.cursor()

        c.execute('SELECT * FROM players WHERE user_id = ?', (user_id,))
        player = c.fetchone()

        conn.close()

        if player:
            return {
                'user_id': player[0],
                'nickname': player[1],
                'avatar': player[2],
                'total_taps': player[3],
                'best_score': player[4],
                'tap_power': player[5]
            }
        return None

    def get_leaderboard(self, limit=500):
        """Получение таблицы лидеров"""
        conn = sqlite3.connect(self.db_file)
        c = conn.cursor()

        c.execute('''SELECT p.user_id, p.nickname, p.avatar, l.taps_per_minute
                    FROM players p
                    JOIN (
                        SELECT user_id, MAX(taps_per_minute) as taps_per_minute
                        FROM leaderboard
                        GROUP BY user_id
                    ) l ON p.user_id = l.user_id
                    ORDER BY l.taps_per_minute DESC
                    LIMIT ?''', (limit,))
        
        leaderboard = [{
            'user_id': row[0],
            'nickname': row[1],
            'avatar': row[2],
            'tapsPerMinute': row[3]
        } for row in c.fetchall()]

        conn.close()
        return leaderboard

    def complete_task(self, user_id, task_id):
        """Отметка о выполнении задания"""
        conn = sqlite3.connect(self.db_file)
        c = conn.cursor()

        c.execute('''INSERT INTO completed_tasks (user_id, task_id, completed_at)
                    VALUES (?, ?, ?)''',
                 (user_id, task_id, datetime.now()))

        conn.commit()
        conn.close()

    def get_completed_tasks(self, user_id):
        """Получение списка выполненных заданий"""
        conn = sqlite3.connect(self.db_file)
        c = conn.cursor()

        c.execute('SELECT task_id FROM completed_tasks WHERE user_id = ?', (user_id,))
        tasks = [row[0] for row in c.fetchall()]

        conn.close()
        return tasks

    def cleanup_old_records(self, days=30):
        """Очистка старых записей из таблицы лидеров"""
        conn = sqlite3.connect(self.db_file)
        c = conn.cursor()

        c.execute('''DELETE FROM leaderboard 
                    WHERE timestamp < datetime('now', '-? days')''', (days,))

        conn.commit()
        conn.close()