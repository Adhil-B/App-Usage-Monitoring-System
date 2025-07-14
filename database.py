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
    c.execute('''
        CREATE TABLE IF NOT EXISTS website_usage_logs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            site TEXT,
            browser TEXT,
            start_time TEXT,
            end_time TEXT,
            duration REAL
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
    # Normalize app_name for storage
    norm_app_name = app_name.lower().replace('.exe', '')
    conn = get_connection()
    c = conn.cursor()
    c.execute('''
        INSERT INTO limits (app_name, max_minutes) VALUES (?, ?)
        ON CONFLICT(app_name) DO UPDATE SET max_minutes=excluded.max_minutes
    ''', (norm_app_name, max_minutes))
    conn.commit()
    conn.close()

def get_limit(app_name):
    # Normalize app_name for lookup
    norm_app_name = app_name.lower().replace('.exe', '')
    conn = get_connection()
    c = conn.cursor()
    c.execute('SELECT max_minutes FROM limits WHERE app_name=?', (norm_app_name,))
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

def log_website_usage(site, browser, start_time, end_time, duration):
    conn = get_connection()
    c = conn.cursor()
    c.execute('''
        INSERT INTO website_usage_logs (site, browser, start_time, end_time, duration)
        VALUES (?, ?, ?, ?, ?)
    ''', (site, browser, start_time, end_time, duration))
    conn.commit()
    conn.close()

def get_website_usage_today():
    conn = get_connection()
    c = conn.cursor()
    today = datetime.now().strftime('%Y-%m-%d')
    c.execute('''
        SELECT site, SUM(duration) FROM website_usage_logs
        WHERE start_time LIKE ?
        GROUP BY site
        ORDER BY SUM(duration) DESC
    ''', (today+'%',))
    results = c.fetchall()
    conn.close()
    return results

def get_top_websites(limit=10):
    conn = get_connection()
    c = conn.cursor()
    c.execute('''
        SELECT site, SUM(duration) as total FROM website_usage_logs
        GROUP BY site
        ORDER BY total DESC
        LIMIT ?
    ''', (limit,))
    results = c.fetchall()
    conn.close()
    return results

def get_usage_range(start_date, end_date):
    """Get app usage between two dates (inclusive), grouped by app and day."""
    conn = get_connection()
    c = conn.cursor()
    c.execute('''
        SELECT app_name, start_time, SUM(duration) FROM usage_logs
        WHERE date(start_time) BETWEEN ? AND ?
        GROUP BY app_name, date(start_time)
        ORDER BY date(start_time), SUM(duration) DESC
    ''', (start_date, end_date))
    results = c.fetchall()
    conn.close()
    return results

def get_usage_by_hour(date_str):
    """Get app usage for a specific date, grouped by hour."""
    conn = get_connection()
    c = conn.cursor()
    c.execute('''
        SELECT strftime('%H', start_time) as hour, app_name, SUM(duration) FROM usage_logs
        WHERE date(start_time) = ?
        GROUP BY hour, app_name
        ORDER BY hour, SUM(duration) DESC
    ''', (date_str,))
    results = c.fetchall()
    conn.close()
    return results

def get_usage_by_day(start_date, end_date):
    """Get total app usage per day in a date range."""
    conn = get_connection()
    c = conn.cursor()
    c.execute('''
        SELECT date(start_time) as day, app_name, SUM(duration) FROM usage_logs
        WHERE date(start_time) BETWEEN ? AND ?
        GROUP BY day, app_name
        ORDER BY day, SUM(duration) DESC
    ''', (start_date, end_date))
    results = c.fetchall()
    conn.close()
    return results

def get_usage_by_week(start_date, end_date):
    """Get total app usage per week in a date range."""
    conn = get_connection()
    c = conn.cursor()
    c.execute('''
        SELECT strftime('%Y-%W', start_time) as week, app_name, SUM(duration) FROM usage_logs
        WHERE date(start_time) BETWEEN ? AND ?
        GROUP BY week, app_name
        ORDER BY week, SUM(duration) DESC
    ''', (start_date, end_date))
    results = c.fetchall()
    conn.close()
    return results

def get_website_usage_range(start_date, end_date):
    conn = get_connection()
    c = conn.cursor()
    c.execute('''
        SELECT site, start_time, SUM(duration) FROM website_usage_logs
        WHERE date(start_time) BETWEEN ? AND ?
        GROUP BY site, date(start_time)
        ORDER BY date(start_time), SUM(duration) DESC
    ''', (start_date, end_date))
    results = c.fetchall()
    conn.close()
    return results

def get_website_usage_by_hour(date_str):
    conn = get_connection()
    c = conn.cursor()
    c.execute('''
        SELECT strftime('%H', start_time) as hour, site, SUM(duration) FROM website_usage_logs
        WHERE date(start_time) = ?
        GROUP BY hour, site
        ORDER BY hour, SUM(duration) DESC
    ''', (date_str,))
    results = c.fetchall()
    conn.close()
    return results

def get_website_usage_by_day(start_date, end_date):
    conn = get_connection()
    c = conn.cursor()
    c.execute('''
        SELECT date(start_time) as day, site, SUM(duration) FROM website_usage_logs
        WHERE date(start_time) BETWEEN ? AND ?
        GROUP BY day, site
        ORDER BY day, SUM(duration) DESC
    ''', (start_date, end_date))
    results = c.fetchall()
    conn.close()
    return results

def get_website_usage_by_week(start_date, end_date):
    conn = get_connection()
    c = conn.cursor()
    c.execute('''
        SELECT strftime('%Y-%W', start_time) as week, site, SUM(duration) FROM website_usage_logs
        WHERE date(start_time) BETWEEN ? AND ?
        GROUP BY week, site
        ORDER BY week, SUM(duration) DESC
    ''', (start_date, end_date))
    results = c.fetchall()
    conn.close()
    return results 