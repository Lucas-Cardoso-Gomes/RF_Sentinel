import threading
from utils.logger import logger

capture_lock = threading.Lock()

SHARED_STATUS = {
    "hackrf_status": {"connected": False, "status_text": "Verificando..."},
    "next_pass": None,
    "scheduler_log": logger.shared_log,
    "manual_capture_active": False
}

scanner_event = threading.Event()
scanner_event.set()

scheduler_thread = None