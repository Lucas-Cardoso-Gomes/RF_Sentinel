import sqlite3
from pathlib import Path
import datetime

DB_FILE = Path("data") / "signals.db"
DB_FILE.parent.mkdir(exist_ok=True)

def get_connection():
    conn = sqlite3.connect(DB_FILE)
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    with get_connection() as conn:
        cur = conn.cursor()
        cur.execute('''
            CREATE TABLE IF NOT EXISTS signals (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                target TEXT,
                frequency INTEGER,
                timestamp TEXT,
                file_path TEXT
            )
        ''')
        conn.commit()

def insert_signal(target: str, frequency: int, file_path: str):
    with get_connection() as conn:
        cur = conn.cursor()
        cur.execute('''
            INSERT INTO signals (target, frequency, timestamp, file_path)
            VALUES (?, ?, ?, ?)
        ''', (target, frequency, datetime.datetime.utcnow().isoformat(), file_path))
        conn.commit()
