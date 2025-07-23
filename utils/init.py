from backend.db import init_db
from utils.rfscanner import start_scanner

# Executado na inicialização
init_db()
start_scanner()
