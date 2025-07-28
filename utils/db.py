# utils/db.py
import sqlite3
import os

DB_FILE = "signals.db"

def init_db():
    # (nenhuma alteração nesta função)
    if not os.path.exists(DB_FILE):
        print("Criando banco de dados 'signals.db'...")
    
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    
    cursor.execute(
        """
        CREATE TABLE IF NOT EXISTS signals (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            target TEXT NOT NULL,
            frequency REAL NOT NULL,
            timestamp TEXT NOT NULL,
            filepath TEXT NOT NULL UNIQUE,
            image_path TEXT
        );
        """
    )
    
    try:
        cursor.execute("ALTER TABLE signals ADD COLUMN image_path TEXT")
    except sqlite3.OperationalError:
        pass

    conn.commit()
    conn.close()

def get_db_connection():
    # (nenhuma alteração nesta função)
    conn = sqlite3.connect(DB_FILE)
    conn.row_factory = sqlite3.Row
    return conn

def insert_signal(target, frequency, timestamp, filepath, image_path=None):
    # (nenhuma alteração nesta função)
    try:
        conn = get_db_connection()
        conn.execute(
            "INSERT INTO signals (target, frequency, timestamp, filepath, image_path) VALUES (?, ?, ?, ?, ?)",
            (target, frequency, timestamp, filepath, image_path),
        )
        conn.commit()
        conn.close()
    except sqlite3.Error as e:
        print(f"❌ Erro no banco de dados ao inserir sinal: {e}")

# --- NOVA FUNÇÃO ---
def get_signal_paths_by_id(signal_id: int):
    """Busca os caminhos do arquivo .wav e da imagem de um sinal pelo seu ID."""
    try:
        conn = get_db_connection()
        signal = conn.execute("SELECT filepath, image_path FROM signals WHERE id = ?", (signal_id,)).fetchone()
        conn.close()
        return dict(signal) if signal else None
    except sqlite3.Error as e:
        print(f"❌ Erro no banco de dados ao buscar caminhos do sinal: {e}")
        return None

# --- NOVA FUNÇÃO ---
def delete_signal_by_id(signal_id: int):
    """Remove um sinal do banco de dados pelo seu ID."""
    try:
        conn = get_db_connection()
        conn.execute("DELETE FROM signals WHERE id = ?", (signal_id,))
        conn.commit()
        conn.close()
        return True
    except sqlite3.Error as e:
        print(f"❌ Erro no banco de dados ao deletar sinal: {e}")
        return False

def get_latest_signals(limit=15):
    # (aumentado o limite padrão)
    try:
        conn = get_db_connection()
        signals = conn.execute(
            "SELECT * FROM signals ORDER BY id DESC LIMIT ?", (limit,)
        ).fetchall()
        conn.close()
        return [dict(row) for row in signals]
    except sqlite3.Error as e:
        print(f"❌ Erro no banco de dados ao buscar sinais: {e}")
        return []

# Removida a função delete_signal_by_filepath pois a deleção por ID é mais segura.