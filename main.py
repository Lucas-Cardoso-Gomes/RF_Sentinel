# main.py
import sys
import os
import threading
import uvicorn # <-- 1. Importe o uvicorn

# Adiciona o diretório raiz do projeto ao path do Python.
sys.path.insert(0, os.path.abspath(os.path.dirname(__file__)))

from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates

from utils import db
from utils.scheduler import scheduler_loop

# Inicializa o banco de dados
db.init_db()

# Evento para controlar o scanner de forma segura
scanner_event = threading.Event()
scanner_event.set()  # Inicia como ativo

# Inicia a thread do agendador
scheduler_thread = threading.Thread(target=scheduler_loop, args=(scanner_event,))
scheduler_thread.daemon = True
scheduler_thread.start()

app = FastAPI(title="RFSentinel")

templates = Jinja2Templates(directory="templates")

@app.get("/", response_class=HTMLResponse)
async def read_root(request: Request):
    """Serve a página principal com o status e os sinais."""
    signals = db.get_latest_signals(10)
    status = "Ativo" if scanner_event.is_set() else "Parado"
    return templates.TemplateResponse(
        "index.html",
        {"request": request, "signals": signals, "status": status},
    )

@app.get("/api/signals")
def get_signals():
    """Endpoint da API para fornecer os sinais mais recentes."""
    return db.get_latest_signals(10)

@app.post("/scanner/toggle")
def toggle_scanner():
    """Endpoint para ativar/desativar o scanner."""
    if scanner_event.is_set():
        scanner_event.clear()  # Pausa o scanner
        status = "Parado"
    else:
        scanner_event.set()  # Retoma o scanner
        status = "Ativo"
    return {"status": status}


# --- INÍCIO DA ADIÇÃO ---
# 2. Adicione este bloco no final do arquivo
if __name__ == "__main__":
    print("Iniciando o servidor web Uvicorn...")
    uvicorn.run(
        "main:app",         # 'main' é o nome do arquivo (main.py), 'app' é o objeto FastAPI
        host="127.0.0.1",   # Endereço para rodar o servidor
        port=8000,          # Porta que você vai acessar no navegador
        reload=True         # Reinicia o servidor automaticamente quando você salvar uma alteração no código
    )
# --- FIM DA ADIÇÃO ---