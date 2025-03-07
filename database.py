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
        self.sync_data()  # Синхронизируем данные между SQLite и JSON

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

        try:
            # Начинаем транзакцию
            c.execute('BEGIN TRANSACTION')

            # Создаем таблицу игроков, если она не существует
            c.execute('''CREATE TABLE IF NOT EXISTS players
                        (user_id INTEGER PRIMARY KEY,
                         nickname TEXT,
                         avatar TEXT,
                         total_taps INTEGER DEFAULT 0,
                         best_score INTEGER DEFAULT 0,
                         tap_power INTEGER DEFAULT 1,
                         taps_per_minute INTEGER DEFAULT 0,
                         last_updated TIMESTAMP)''')

            # Создаем индекс, если он не существует
            c.execute('''CREATE INDEX IF NOT EXISTS idx_taps_per_minute 
                        ON players(taps_per_minute DESC)''')

            # Создаем таблицу истории результатов, если она не существует
            c.execute('''CREATE TABLE IF NOT EXISTS score_history
                        (user_id INTEGER,
                         score INTEGER,
                         timestamp TIMESTAMP,
                         FOREIGN KEY(user_id) REFERENCES players(user_id))''')

            # Создаем таблицу выполненных заданий, если она не существует
            c.execute('''CREATE TABLE IF NOT EXISTS completed_tasks
                        (user_id INTEGER,
                         task_id TEXT,
                         completed_at TIMESTAMP,
                         FOREIGN KEY(user_id) REFERENCES players(user_id))''')

            # Завершаем транзакцию
            conn.commit()

        except Exception as e:
            # В случае ошибки откатываем изменения
            conn.rollback()
            raise e

        finally:
            conn.close()

    def sync_data(self):
        """Синхронизация данных между SQLite и JSON"""
        conn = sqlite3.connect(self.db_file)
        c = conn.cursor()

        try:
            # Получаем все записи из SQLite
            c.execute('SELECT * FROM players')
            players = c.fetchall()

            # Обновляем JSON данными из SQLite
            for player in players:
                user_id = str(player[0])
                if user_id not in self.players_data:
                    self.players_data[user_id] = {
                        'nickname': player[1],
                        'avatar': player[2],
                        'total_taps': player[3],
                        'best_score': player[4],
                        'tap_power': player[5],
                        'taps_per_minute': player[6],
                        'last_updated': player[7]
                    }

            # Обновляем SQLite данными из JSON
            for user_id, data in self.players_data.items():
                c.execute('''INSERT OR REPLACE INTO players 
                            (user_id, nickname, avatar, total_taps, best_score, tap_power, taps_per_minute, last_updated)
                            VALUES (?, ?, ?, ?, ?, ?, ?, ?)''',
                         (int(user_id), data['nickname'], data['avatar'],
                          data['total_taps'], data['best_score'],
                          data.get('tap_power', 1), data.get('taps_per_minute', 0),
                          data.get('last_updated', datetime.now().isoformat())))

            conn.commit()
            self.save_players_data()

        except Exception as e:
            conn.rollback()
            print(f"Error syncing data: {e}")

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
                # Если игрок существует, сохраняем старые значения для полей, которых нет в новых данных
                current_data = {
                    'nickname': current_player[1] or 'Игрок',
                    'avatar': current_player[2] or 'avatar1',
                    'total_taps': current_player[3] or 0,
                    'best_score': current_player[4] or 0,
                    'tap_power': current_player[5] or 1,
                    'taps_per_minute': current_player[6] or 0
                }
                # Обновляем только предоставленные поля
                current_data.update({k: v for k, v in data.items() if v is not None})
                data = current_data
            
            # Обновляем в SQLite
            c.execute('''INSERT OR REPLACE INTO players 
                        (user_id, nickname, avatar, total_taps, best_score, tap_power, taps_per_minute, last_updated)
                        VALUES (?, ?, ?, ?, ?, ?, ?, ?)''',
                     (user_id, 
                      data.get('nickname', 'Игрок'),
                      data.get('avatar', 'avatar1'),
                      data.get('total_taps', 0),
                      data.get('best_score', 0),
                      data.get('tap_power', 1),
                      data.get('taps_per_minute', 0),
                      datetime.now()))

            if 'score' in data:
                c.execute('''INSERT INTO score_history (user_id, score, timestamp)
                            VALUES (?, ?, ?)''',
                         (user_id, data['score'], datetime.now()))

            conn.commit()

            # Обновляем в JSON
            str_user_id = str(user_id)
            self.players_data[str_user_id] = {
                'nickname': data.get('nickname', 'Игрок'),
                'avatar': data.get('avatar', 'avatar1'),
                'total_taps': data.get('total_taps', 0),
                'best_score': data.get('best_score', 0),
                'tap_power': data.get('tap_power', 1),
                'taps_per_minute': data.get('taps_per_minute', 0),
                'last_updated': datetime.now().isoformat()
            }
            self.save_players_data()

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
            # Пробуем получить из SQLite
            c.execute('SELECT * FROM players WHERE user_id = ?', (user_id,))
            player = c.fetchone()

            if player:
                player_data = {
                    'user_id': player[0],
                    'nickname': player[1] or 'Игрок',
                    'avatar': player[2] or 'avatar1',
                    'total_taps': player[3] or 0,
                    'best_score': player[4] or 0,
                    'tap_power': player[5] or 1,
                    'taps_per_minute': player[6] or 0
                }
                return player_data

            # Если нет в SQLite, проверяем JSON
            str_user_id = str(user_id)
            if str_user_id in self.players_data:
                player_data = {
                    'user_id': user_id,
                    'nickname': self.players_data[str_user_id].get('nickname', 'Игрок'),
                    'avatar': self.players_data[str_user_id].get('avatar', 'avatar1'),
                    'total_taps': self.players_data[str_user_id].get('total_taps', 0),
                    'best_score': self.players_data[str_user_id].get('best_score', 0),
                    'tap_power': self.players_data[str_user_id].get('tap_power', 1),
                    'taps_per_minute': self.players_data[str_user_id].get('taps_per_minute', 0)
                }
                # Сохраняем в SQLite для синхронизации
                self.update_player(user_id, player_data)
                return player_data

            # Если игрок не найден нигде, создаем нового
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

    def get_leaderboard(self, limit=500):
        """Получение таблицы лидеров"""
        conn = sqlite3.connect(self.db_file)
        c = conn.cursor()

        try:
            # Получаем данные из SQLite
            c.execute('''SELECT user_id, nickname, avatar, taps_per_minute 
                        FROM players 
                        WHERE taps_per_minute > 0 
                        ORDER BY taps_per_minute DESC 
                        LIMIT ?''', (limit,))
            
            players = []
            for row in c.fetchall():
                players.append({
                    'user_id': row[0],
                    'nickname': row[1],
                    'avatar': row[2],
                    'tapsPerMinute': row[3]
                })
            
            return players

        finally:
            conn.close()

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