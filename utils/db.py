# utils/db.py
import sqlite3
import os

DB_FILE = "signals.db"

def init_db():
    """Inicializa o banco de dados e cria a tabela se não existir."""
    if not os.path.exists(DB_FILE):
        print("Criando banco de dados 'signals.db'...")
        try:
            conn = sqlite3.connect(DB_FILE)
            cursor = conn.cursor()
            cursor.execute(
                """
                CREATE TABLE signals (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    target TEXT NOT NULL,
                    frequency REAL NOT NULL,
                    timestamp TEXT NOT NULL,
                    filepath TEXT NOT NULL
                );
                """
            )
            conn.commit()
            conn.close()
            print("Banco de dados criado com sucesso.")
        except sqlite3.Error as e:
            print(f"❌ Erro ao criar o banco de dados: {e}")


def get_db_connection():
    """Retorna uma conexão com o banco de dados."""
    conn = sqlite3.connect(DB_FILE)
    # Permite acessar colunas pelo nome (ex: row['target'])
    conn.row_factory = sqlite3.Row
    return conn


def insert_signal(target, frequency, timestamp, filepath):
    """Insere um novo sinal capturado no banco de dados."""
    try:
        conn = get_db_connection()
        conn.execute(
            "INSERT INTO signals (target, frequency, timestamp, filepath) VALUES (?, ?, ?, ?)",
            (target, frequency, timestamp, filepath),
        )
        conn.commit()
        conn.close()
    except sqlite3.Error as e:
        print(f"❌ Erro no banco de dados ao inserir sinal: {e}")


def get_latest_signals(limit=10):
    """Retorna os últimos N sinais capturados."""
    try:
        conn = get_db_connection()
        signals = conn.execute(
            "SELECT * FROM signals ORDER BY id DESC LIMIT ?", (limit,)
        ).fetchall()
        conn.close()
        # Converte os resultados para uma lista de dicionários
        return [dict(row) for row in signals]
    except sqlite3.Error as e:
        print(f"❌ Erro no banco de dados ao buscar sinais: {e}")
        return []