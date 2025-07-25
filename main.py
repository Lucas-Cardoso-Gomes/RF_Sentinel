# main.py
import sys
import os
import threading

sys.path.insert(0, os.path.abspath(os.path.dirname(__file__)))

from utils.win_dll_fix import apply as apply_win_dll_fix
apply_win_dll_fix() 

from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates

from utils import db
from utils.scheduler import scheduler_loop

# --- NOVIDADE: Variável para armazenar o estado do Hardware ---
HACKRF_STATUS = {"connected": False, "status_text": "Verificando..."}

db.init_db()

scanner_event = threading.Event()
scanner_event.set()

# --- ALTERAÇÃO: Passamos o dicionário de status para a thread ---
scheduler_thread = threading.Thread(
    target=scheduler_loop, args=(scanner_event, HACKRF_STATUS)
)
scheduler_thread.daemon = True
scheduler_thread.start()

app = FastAPI(title="RFSentinel")
templates = Jinja2Templates(directory="templates")

@app.get("/", response_class=HTMLResponse)
async def read_root(request: Request):
    """Serve a página principal com o status e os sinais."""
    signals = db.get_latest_signals(10)
    scanner_status = "Ativo" if scanner_event.is_set() else "Parado"
    return templates.TemplateResponse(
        "index.html",
        {
            "request": request,
            "signals": signals,
            "scanner_status": scanner_status,
            # Passa o status inicial do HackRF para a página
            "hackrf_status_text": HACKRF_STATUS["status_text"],
            "hackrf_connected": HACKRF_STATUS["connected"],
        },
    )

# --- NOVO ENDPOINT ---
@app.get("/api/status")
def get_status():
    """Retorna o status combinado do scanner e do hardware."""
    return {
        "scanner_status": "Ativo" if scanner_event.is_set() else "Parado",
        "hackrf_status": HACKRF_STATUS,
    }

@app.get("/api/signals")
def get_signals():
    """Endpoint da API para fornecer os sinais mais recentes."""
    return db.get_latest_signals(10)

@app.post("/scanner/toggle")
def toggle_scanner():
    """Endpoint para ativar/desativar o scanner."""
    if scanner_event.is_set():
        scanner_event.clear()
        status = "Parado"
    else:
        scanner_event.set()
        status = "Ativo"
    return {"status": status}

if __name__ == "__main__":
    import uvicorn
    print("Iniciando o servidor web Uvicorn...")
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=False)