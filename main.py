import sys
import os
import uvicorn

sys.path.insert(0, os.path.abspath(os.path.dirname(__file__)))

os.environ['LIBUSB_DEBUG'] = '0'
from utils.win_dll_fix import apply as apply_win_dll_fix
apply_win_dll_fix() 

from utils import db
from utils.scheduler import Scheduler
from utils.logger import logger

import app_state

if __name__ == "__main__":
    db.init_db()

    app_state.scheduler_thread = Scheduler(app_state.scanner_event, app_state.SHARED_STATUS)
    
    app_state.scheduler_thread.start()

    from web import app

    logger.log("Iniciando o servidor web Uvicorn...", "INFO")
    uvicorn.run(
        app, 
        host="0.0.0.0", 
        port=8000, 
        reload=False, 
        log_level="info"
    )