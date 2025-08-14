import datetime
import threading

class Logger:
    _instance = None
    _lock = threading.Lock()
    def __new__(cls):
        with cls._lock:
            if cls._instance is None:
                cls._instance = super(Logger, cls).__new__(cls)
                cls._instance._initialized = False
        return cls._instance
    def __init__(self):
        if self._initialized: return
        self.log_colors = {'INFO': '\033[94m', 'SUCCESS': '\033[92m', 'WARN': '\033[93m', 'ERROR': '\033[91m', 'DEBUG': '\033[95m', 'RESET': '\033[0m'}
        self.shared_log = []
        self._initialized = True
    def _add_to_shared_log(self, log_entry):
        self.shared_log.append(log_entry)
        if len(self.shared_log) > 30: self.shared_log.pop(0)
    def log(self, message, level='INFO'):
        timestamp = datetime.datetime.now().strftime('%H:%M:%S')
        color = self.log_colors.get(level, '')
        reset_color = self.log_colors['RESET']
        print(f"{color}[{timestamp}][{level.ljust(7)}] {message}{reset_color}")
        log_entry = { "timestamp": timestamp, "level": level, "message": message }
        self._add_to_shared_log(log_entry)

logger = Logger()