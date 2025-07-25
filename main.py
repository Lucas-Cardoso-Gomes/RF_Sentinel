# main.py
import sys
import os
import threading
import json

# Silencia os logs do libusb
os.environ['LIBUSB_DEBUG'] = '0'

sys.path.insert(0, os.path.abspath(os.path.dirname(__file__)))

from utils.win_dll_fix import apply as apply_win_dll_fix
apply_win_dll_fix() 

from fastapi import FastAPI, Request, WebSocket, WebSocketDisconnect
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.templating import Jinja2Templates
from fastapi.staticfiles import StaticFiles
import numpy as np
import SoapySDR
from SoapySDR import *
import asyncio

from utils import db
from utils.scheduler import scheduler_loop
from utils.scanner import real_capture # Importamos para a captura manual

# --- Dicionário de estado compartilhado para comunicação entre threads ---
SHARED_STATUS = {
    "hackrf_status": {"connected": False, "status_text": "Verificando..."},
    "next_pass": None, # Ex: {'name': 'NOAA 19', 'start_utc': '...'}
    "scheduler_log": [], # Lista das últimas mensagens de log
    "manual_capture_active": False # Flag para captura manual
}

db.init_db()

scanner_event = threading.Event()
scanner_event.set()

# Passa o dicionário de status completo para a thread do agendador
scheduler_thread = threading.Thread(
    target=scheduler_loop, args=(scanner_event, SHARED_STATUS)
)
scheduler_thread.daemon = True
scheduler_thread.start()

app = FastAPI(title="RFSentinel")
templates = Jinja2Templates(directory="templates")

# Monta a pasta de capturas para que o navegador possa acessar os arquivos
app.mount("/captures", StaticFiles(directory="captures"), name="captures")

# --- LÓGICA PARA CAPTURA MANUAL ---
def run_manual_capture(target_info):
    SHARED_STATUS["manual_capture_active"] = True
    print(f"Iniciando captura manual para: {target_info}")
    real_capture(target_info)
    print("Captura manual finalizada.")
    SHARED_STATUS["manual_capture_active"] = False

@app.post("/api/capture/manual")
async def manual_capture_endpoint(request: Request):
    if SHARED_STATUS["manual_capture_active"]:
        return JSONResponse(content={"error": "Uma captura manual já está em andamento."}, status_code=409)
    
    data = await request.json()
    target_info = {
        "name": data.get("name", "ManualCapture"),
        "frequency": int(float(data.get("frequency_mhz", 0)) * 1e6),
        "capture_duration_seconds": int(data.get("duration_sec", 10))
    }

    # Inicia a captura em uma nova thread para não bloquear a API
    capture_thread = threading.Thread(target=run_manual_capture, args=(target_info,))
    capture_thread.start()

    return {"status": "Captura manual iniciada."}

# --- ENDPOINTS DA API E DA INTERFACE ---

@app.get("/", response_class=HTMLResponse)
async def read_root(request: Request):
    """Serve a página principal do dashboard."""
    return templates.TemplateResponse("index.html", {"request": request})

@app.get("/api/status")
def get_status():
    """Retorna o status combinado de todo o sistema para o frontend."""
    return {
        "scanner_status": "Ativo" if scanner_event.is_set() else "Parado",
        "hackrf_status": SHARED_STATUS["hackrf_status"],
        "next_pass": SHARED_STATUS["next_pass"],
        "scheduler_log": SHARED_STATUS["scheduler_log"],
        "manual_capture_active": SHARED_STATUS["manual_capture_active"]
    }

@app.get("/api/signals")
def get_signals():
    """Fornece a lista das últimas capturas do banco de dados."""
    return db.get_latest_signals(10)

@app.post("/scanner/toggle")
def toggle_scanner():
    """Ativa ou desativa o agendador de satélites."""
    if scanner_event.is_set():
        scanner_event.clear()
        status = "Parado"
    else:
        scanner_event.set()
        status = "Ativo"
    return {"status": status}

@app.websocket("/ws/waterfall")
async def websocket_endpoint(websocket: WebSocket):
    """Endpoint WebSocket para o waterfall interativo."""
    await websocket.accept()
    sdr = None
    rxStream = None
    try:
        sdr_devices = SoapySDR.Device.enumerate()
        hackrf_device = next((dev for dev in sdr_devices if 'driver' in dev and dev['driver'] == 'hackrf'), None)
        
        if not hackrf_device: raise RuntimeError("HackRF não encontrado.")
        
        sdr = SoapySDR.Device(hackrf_device)
        sdr.setSampleRate(SOAPY_SDR_RX, 0, 2.4e6)
        sdr.setFrequency(SOAPY_SDR_RX, 0, 101.1e6)
        sdr.setGain(SOAPY_SDR_RX, 0, 32)

        rxStream = sdr.setupStream(SOAPY_SDR_RX, SOAPY_SDR_CF32)
        sdr.activateStream(rxStream)
        
        fft_size = 1024
        samples = np.zeros(fft_size, np.complex64)

        async def rx_loop(): # Loop que lê dados do SDR e envia para o cliente
            while True:
                sdr.readStream(rxStream, [samples], len(samples))
                fft_result = np.fft.fftshift(np.fft.fft(samples))
                psd = np.abs(fft_result)**2
                psd_db = 10 * np.log10(psd / (fft_size**2))
                await websocket.send_json(psd_db.tolist())
                await asyncio.sleep(0.05)

        async def tx_loop(): # Loop que recebe comandos do cliente e atualiza o SDR
            while True:
                message = await websocket.receive_text()
                data = json.loads(message)
                if 'frequency' in data:
                    print(f"Waterfall: Mudando frequência para {data['frequency']/1e6:.2f} MHz")
                    sdr.setFrequency(SOAPY_SDR_RX, 0, float(data['frequency']))
                if 'gain' in data:
                    print(f"Waterfall: Mudando ganho para {data['gain']} dB")
                    sdr.setGain(SOAPY_SDR_RX, 0, int(data['gain']))

        # Executa as duas tarefas concorrentemente
        await asyncio.gather(rx_loop(), tx_loop())

    except WebSocketDisconnect:
        print("Cliente WebSocket desconectado.")
    except Exception as e:
        print(f"Erro no WebSocket: {e}")
    finally:
        if sdr and rxStream:
            sdr.deactivateStream(rxStream)
            sdr.closeStream(rxStream)
            print("Stream do SDR para o waterfall foi fechado.")

if __name__ == "__main__":
    import uvicorn
    print("Iniciando o servidor web Uvicorn...")
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=False)