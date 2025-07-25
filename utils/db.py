# utils/db.py
import sqlite3
import os

DB_FILE = "signals.db"

def init_db():
    """Inicializa o banco de dados e cria a tabela se não existir."""
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    # Adiciona a coluna image_path
    try:
        cursor.execute("ALTER TABLE signals ADD COLUMN image_path TEXT")
        print("Coluna 'image_path' adicionada ao banco de dados.")
    except sqlite3.OperationalError:
        # A coluna já existe, ignora o erro
        pass

    if not os.path.exists(DB_FILE):
        print("Criando banco de dados 'signals.db'...")
        try:
            cursor.execute(
                """
                CREATE TABLE signals (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    target TEXT NOT NULL,
                    frequency REAL NOT NULL,
                    timestamp TEXT NOT NULL,
                    filepath TEXT NOT NULL,
                    image_path TEXT
                );
                """
            )
            conn.commit()
            print("Banco de dados criado com sucesso.")
        except sqlite3.Error as e:
            print(f"❌ Erro ao criar o banco de dados: {e}")
    conn.close()


def get_db_connection():
    # (sem alterações)
    conn = sqlite3.connect(DB_FILE)
    conn.row_factory = sqlite3.Row
    return conn

def insert_signal(target, frequency, timestamp, filepath, image_path=None):
    """Insere um novo sinal capturado no banco de dados."""
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


def get_latest_signals(limit=10):
    # (sem alterações)
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