import sqlite3
from datetime import datetime

DB_NAME = 'app_usage.db'

def get_connection():
    return sqlite3.connect(DB_NAME, isolation_level=None)

def init_db():
    conn = get_connection()
    c = conn.cursor()
    c.execute('PRAGMA journal_mode=WAL;')
    c.execute('''
        CREATE TABLE IF NOT EXISTS usage_logs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            app_name TEXT,
            title TEXT,
            start_time TEXT,
            end_time TEXT,
            duration REAL
        )
    ''')
    c.execute('''
        CREATE TABLE IF NOT EXISTS limits (
            app_name TEXT PRIMARY KEY,
            max_minutes INTEGER
        )
    ''')
    conn.commit()
    conn.close()

def insert_usage_log(app_name, title, start_time, end_time, duration):
    conn = get_connection()
    c = conn.cursor()
    c.execute('''
        INSERT INTO usage_logs (app_name, title, start_time, end_time, duration)
        VALUES (?, ?, ?, ?, ?)
    ''', (app_name, title, start_time, end_time, duration))
    conn.commit()
    conn.close()

def set_limit(app_name, max_minutes):
    conn = get_connection()
    c = conn.cursor()
    c.execute('''
        INSERT INTO limits (app_name, max_minutes) VALUES (?, ?)
        ON CONFLICT(app_name) DO UPDATE SET max_minutes=excluded.max_minutes
    ''', (app_name, max_minutes))
    conn.commit()
    conn.close()

def get_limit(app_name):
    conn = get_connection()
    c = conn.cursor()
    c.execute('SELECT max_minutes FROM limits WHERE app_name=?', (app_name,))
    row = c.fetchone()
    conn.close()
    return row[0] if row else None

def get_usage_today():
    conn = get_connection()
    c = conn.cursor()
    today = datetime.now().strftime('%Y-%m-%d')
    c.execute('''
        SELECT app_name, SUM(duration) FROM usage_logs
        WHERE start_time LIKE ?
        GROUP BY app_name
        ORDER BY SUM(duration) DESC
    ''', (today+'%',))
    results = c.fetchall()
    conn.close()
    return results

def get_top_used_apps(limit=5):
    conn = get_connection()
    c = conn.cursor()
    c.execute('''
        SELECT app_name, SUM(duration) as total FROM usage_logs
        GROUP BY app_name
        ORDER BY total DESC
        LIMIT ?
    ''', (limit,))
    results = c.fetchall()
    conn.close()
    return results

def get_latest_window_titles():
    conn = get_connection()
    c = conn.cursor()
    c.execute('''
        SELECT app_name, title FROM usage_logs
        WHERE id IN (
            SELECT MAX(id) FROM usage_logs GROUP BY app_name
        )
    ''')
    results = dict(c.fetchall())
    conn.close()
    return results 