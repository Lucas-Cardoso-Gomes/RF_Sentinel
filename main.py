# main.py
import sys
import os
import uvicorn

# Adiciona o diretório do projeto ao path do sistema
sys.path.insert(0, os.path.abspath(os.path.dirname(__file__)))

# Configurações iniciais
os.environ['LIBUSB_DEBUG'] = '0'
from utils.win_dll_fix import apply as apply_win_dll_fix
apply_win_dll_fix() 

# Módulos principais da aplicação
from utils import db
from utils.scheduler import Scheduler
from utils.logger import logger

# CORREÇÃO: Importa o módulo de estado compartilhado
import app_state

# --- Ponto de Entrada Principal da Aplicação ---
if __name__ == "__main__":
    # Inicializa o banco de dados
    db.init_db()

    # Cria a instância do agendador e a armazena no módulo de estado
    app_state.scheduler_thread = Scheduler(app_state.scanner_event, app_state.SHARED_STATUS)
    
    # Inicia a thread do agendador em segundo plano
    app_state.scheduler_thread.start()

    # Importa a aplicação FastAPI do módulo web
    from web import app

    # Inicia o servidor web Uvicorn
    logger.log("Iniciando o servidor web Uvicorn...", "INFO")
    uvicorn.run(
        app, 
        host="0.0.0.0", 
        port=8000, 
        reload=False, 
        log_level="info"
    )