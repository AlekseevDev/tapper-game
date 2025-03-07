import sqlite3
from datetime import datetime, timedelta
import os
import json

class Database:
    def __init__(self, db_file):
        self.db_file = db_file
        self.data_dir = 'game_data'
        self.players_file = os.path.join(self.data_dir, 'players.json')
        self.ensure_data_dir()
        self.init_db()
        self.load_players_data()

    def ensure_data_dir(self):
        """Создание директории для хранения данных"""
        if not os.path.exists(self.data_dir):
            os.makedirs(self.data_dir)
        if not os.path.exists(self.players_file):
            with open(self.players_file, 'w', encoding='utf-8') as f:
                json.dump({}, f)

    def load_players_data(self):
        """Загрузка данных игроков из JSON"""
        try:
            with open(self.players_file, 'r', encoding='utf-8') as f:
                self.players_data = json.load(f)
        except Exception as e:
            print(f"Error loading players data: {e}")
            self.players_data = {}

    def save_players_data(self):
        """Сохранение данных игроков в JSON"""
        try:
            with open(self.players_file, 'w', encoding='utf-8') as f:
                json.dump(self.players_data, f, ensure_ascii=False, indent=2)
        except Exception as e:
            print(f"Error saving players data: {e}")

    def init_db(self):
        """Инициализация базы данных"""
        conn = sqlite3.connect(self.db_file)
        c = conn.cursor()

        # Создаем таблицу игроков с индексом по taps_per_minute
        c.execute('''CREATE TABLE IF NOT EXISTS players
                    (user_id INTEGER PRIMARY KEY,
                     nickname TEXT,
                     avatar TEXT,
                     total_taps INTEGER DEFAULT 0,
                     best_score INTEGER DEFAULT 0,
                     tap_power INTEGER DEFAULT 1,
                     taps_per_minute INTEGER DEFAULT 0,
                     last_updated TIMESTAMP)''')

        # Создаем индекс для быстрой сортировки по taps_per_minute
        c.execute('''CREATE INDEX IF NOT EXISTS idx_taps_per_minute 
                    ON players(taps_per_minute DESC)''')

        # Создаем таблицу истории результатов
        c.execute('''CREATE TABLE IF NOT EXISTS score_history
                    (user_id INTEGER,
                     score INTEGER,
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
        # Обновляем данные в JSON
        str_user_id = str(user_id)
        if str_user_id not in self.players_data:
            self.players_data[str_user_id] = {}
        
        player_data = self.players_data[str_user_id]
        player_data.update({
            'nickname': data['nickname'],
            'avatar': data['avatar'],
            'total_taps': data['total_taps'],
            'best_score': data['best_score'],
            'tap_power': data.get('tap_power', 1),
            'taps_per_minute': data.get('taps_per_minute', 0),
            'last_updated': datetime.now().isoformat()
        })
        
        # Сохраняем в JSON
        self.save_players_data()

        # Обновляем в SQLite
        conn = sqlite3.connect(self.db_file)
        c = conn.cursor()

        try:
            c.execute('BEGIN TRANSACTION')
            c.execute('''INSERT OR REPLACE INTO players 
                        (user_id, nickname, avatar, total_taps, best_score, tap_power, taps_per_minute, last_updated)
                        VALUES (?, ?, ?, ?, ?, ?, ?, ?)''',
                     (user_id, data['nickname'], data['avatar'], data['total_taps'],
                      data['best_score'], data.get('tap_power', 1), 
                      data.get('taps_per_minute', 0), datetime.now()))

            if 'score' in data:
                c.execute('''INSERT INTO score_history (user_id, score, timestamp)
                            VALUES (?, ?, ?)''',
                         (user_id, data['score'], datetime.now()))

            conn.commit()

        except Exception as e:
            conn.rollback()
            raise e

        finally:
            conn.close()

    def get_player(self, user_id):
        """Получение данных игрока"""
        # Сначала пробуем получить из JSON
        str_user_id = str(user_id)
        if str_user_id in self.players_data:
            return {
                'user_id': user_id,
                **self.players_data[str_user_id]
            }

        # Если нет в JSON, пробуем из SQLite
        conn = sqlite3.connect(self.db_file)
        c = conn.cursor()

        c.execute('SELECT * FROM players WHERE user_id = ?', (user_id,))
        player = c.fetchone()

        conn.close()

        if player:
            player_data = {
                'user_id': player[0],
                'nickname': player[1],
                'avatar': player[2],
                'total_taps': player[3],
                'best_score': player[4],
                'tap_power': player[5],
                'taps_per_minute': player[6]
            }
            # Сохраняем найденные данные в JSON
            self.players_data[str_user_id] = player_data
            self.save_players_data()
            return player_data

        return None

    def get_leaderboard(self, limit=500):
        """Получение таблицы лидеров"""
        # Получаем данные из JSON и сортируем
        players = []
        for user_id, data in self.players_data.items():
            if data.get('taps_per_minute', 0) > 0:
                players.append({
                    'user_id': int(user_id),
                    'nickname': data['nickname'],
                    'avatar': data['avatar'],
                    'tapsPerMinute': data['taps_per_minute']
                })
        
        # Сортируем по убыванию taps_per_minute
        players.sort(key=lambda x: x['tapsPerMinute'], reverse=True)
        return players[:limit]

    def complete_task(self, user_id, task_id):
        """Отметка о выполнении задания"""
        # Сохраняем в JSON
        str_user_id = str(user_id)
        if str_user_id not in self.players_data:
            self.players_data[str_user_id] = {}
        
        if 'completed_tasks' not in self.players_data[str_user_id]:
            self.players_data[str_user_id]['completed_tasks'] = []
        
        if task_id not in self.players_data[str_user_id]['completed_tasks']:
            self.players_data[str_user_id]['completed_tasks'].append(task_id)
            self.save_players_data()

        # Сохраняем в SQLite
        conn = sqlite3.connect(self.db_file)
        c = conn.cursor()
        c.execute('''INSERT INTO completed_tasks (user_id, task_id, completed_at)
                    VALUES (?, ?, ?)''',
                 (user_id, task_id, datetime.now()))
        conn.commit()
        conn.close()

    def get_completed_tasks(self, user_id):
        """Получение списка выполненных заданий"""
        str_user_id = str(user_id)
        if str_user_id in self.players_data and 'completed_tasks' in self.players_data[str_user_id]:
            return self.players_data[str_user_id]['completed_tasks']
        return []

    def cleanup_old_records(self, days=30):
        """Очистка старых записей"""
        conn = sqlite3.connect(self.db_file)
        c = conn.cursor()

        try:
            c.execute('BEGIN TRANSACTION')
            
            # Очищаем старые записи из истории
            c.execute('''DELETE FROM score_history 
                        WHERE timestamp < datetime('now', '-? days')''', (days,))

            # Очищаем записи неактивных игроков из SQLite
            c.execute('''DELETE FROM players 
                        WHERE last_updated < datetime('now', '-? days')
                        AND total_taps = 0''', (days,))

            # Очищаем старые записи из JSON
            current_time = datetime.now()
            for user_id in list(self.players_data.keys()):
                last_updated = datetime.fromisoformat(self.players_data[user_id].get('last_updated', '2000-01-01'))
                if (current_time - last_updated).days > days and self.players_data[user_id].get('total_taps', 0) == 0:
                    del self.players_data[user_id]
            
            self.save_players_data()
            conn.commit()

        except Exception as e:
            conn.rollback()
            raise e

        finally:
            conn.close()