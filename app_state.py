# app_state.py
import threading
from utils.logger import logger

# --- Estado Compartilhado Global da Aplicação ---
# Este dicionário é compartilhado entre a thread do agendador e a API web
SHARED_STATUS = {
    "hackrf_status": {"connected": False, "status_text": "Verificando..."},
    "next_pass": None,
    "scheduler_log": logger.shared_log,
    "manual_capture_active": False
}

# Evento para controlar o estado (ativo/pausado) do agendador
scanner_event = threading.Event()
scanner_event.set() # Inicia como ativo por padrão

# Variável para armazenar a instância da thread do agendador.
# Será inicializada no main.py
scheduler_thread = None