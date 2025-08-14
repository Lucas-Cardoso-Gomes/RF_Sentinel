import sys
import os
import uvicorn

sys.path.insert(0, os.path.abspath(os.path.dirname(__file__)))

os.environ['LIBUSB_DEBUG'] = '0'
from utils.win_dll_fix import apply as apply_win_dll_fix
apply_win_dll_fix() 

from utils import db
from utils.logger import logger
from web import app # Importa a app diretamente

if __name__ == "__main__":
    # A inicialização da base de dados e da thread foi movida para os eventos de ciclo de vida do FastAPI em web.py
    
    logger.log("Iniciando o servidor web Uvicorn...", "INFO")
    uvicorn.run(
        app, 
        host="0.0.0.0", 
        port=8000, 
        reload=False, 
        log_level="info"
    )