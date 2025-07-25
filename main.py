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
from utils.scanner import real_capture
from utils.sdr_manager import sdr_manager

# --- NOVIDADE: Evento de controle para o waterfall (o "semáforo") ---
waterfall_event = threading.Event()
waterfall_event.set() # Começa "verde" (permitido rodar)

# --- Dicionário de estado compartilhado para comunicação entre threads ---
SHARED_STATUS = {
    "hackrf_status": {"connected": False, "status_text": "Verificando..."},
    "next_pass": None,
    "scheduler_log": [],
    "manual_capture_active": False
}

db.init_db()
scanner_event = threading.Event()
scanner_event.set()

# Passa o evento do waterfall para a thread do agendador
scheduler_thread = threading.Thread(
    target=scheduler_loop, args=(scanner_event, SHARED_STATUS, waterfall_event)
)
scheduler_thread.daemon = True
scheduler_thread.start()

app = FastAPI(title="RFSentinel")
templates = Jinja2Templates(directory="templates")
app.mount("/captures", StaticFiles(directory="captures"), name="captures")

def run_manual_capture(target_info):
    SHARED_STATUS["manual_capture_active"] = True
    waterfall_event.clear() # Pausa o waterfall
    print(f"Iniciando captura manual para: {target_info}")
    real_capture(target_info)
    print("Captura manual finalizada.")
    waterfall_event.set() # Libera o waterfall
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
    capture_thread = threading.Thread(target=run_manual_capture, args=(target_info,))
    capture_thread.start()
    return {"status": "Captura manual iniciada."}

@app.get("/", response_class=HTMLResponse)
async def read_root(request: Request):
    return templates.TemplateResponse("index.html", {"request": request})

@app.get("/api/status")
def get_status():
    return {
        "scanner_status": "Ativo" if scanner_event.is_set() else "Parado",
        "hackrf_status": SHARED_STATUS["hackrf_status"],
        "next_pass": SHARED_STATUS["next_pass"],
        "scheduler_log": SHARED_STATUS["scheduler_log"],
        "manual_capture_active": SHARED_STATUS["manual_capture_active"]
    }

@app.get("/api/signals")
def get_signals():
    return db.get_latest_signals(10)

@app.post("/scanner/toggle")
def toggle_scanner():
    if scanner_event.is_set(): scanner_event.clear()
    else: scanner_event.set()
    return {"status": "Ativo" if scanner_event.is_set() else "Parado"}

@app.websocket("/ws/waterfall")
async def websocket_endpoint(websocket: WebSocket):
    await websocket.accept()
    
    # Adquire o dispositivo SOMENTE se o semáforo estiver verde
    if not waterfall_event.is_set():
        await websocket.close(code=1011, reason="SDR está em uso para uma captura prioritária.")
        return

    sdr = sdr_manager.acquire_device()
    if not sdr:
        await websocket.close(code=1011, reason="Não foi possível adquirir o dispositivo SDR.")
        return
    
    rxStream = None
    try:
        sdr.setSampleRate(SOAPY_SDR_RX, 0, 2.4e6)
        sdr.setFrequency(SOAPY_SDR_RX, 0, 101.1e6)
        sdr.setGain(SOAPY_SDR_RX, 0, 32)
        rxStream = sdr.setupStream(SOAPY_SDR_RX, SOAPY_SDR_CF32)
        sdr.activateStream(rxStream)
        sdr_manager.active_stream = rxStream
        
        fft_size = 1024
        samples = np.zeros(fft_size, np.complex64)

        async def rx_loop():
            while True:
                if not waterfall_event.is_set():
                    print("Waterfall: Recebeu sinal para pausar. Fechando conexão.")
                    await websocket.close(code=1012, reason="SDR requisitado para captura.")
                    break
                
                sdr.readStream(rxStream, [samples], len(samples))
                fft_result = np.fft.fftshift(np.fft.fft(samples))
                psd = np.abs(fft_result)**2
                psd_db = 10 * np.log10(psd / (fft_size**2) + 1e-12) # Evita log de zero
                await websocket.send_json(psd_db.tolist())
                await asyncio.sleep(0.05)

        async def tx_loop():
            while True:
                message = await websocket.receive_text()
                data = json.loads(message)
                if 'frequency' in data:
                    sdr.setFrequency(SOAPY_SDR_RX, 0, float(data['frequency']))
                if 'gain' in data:
                    sdr.setGain(SOAPY_SDR_RX, 0, int(data['gain']))
        
        await asyncio.gather(rx_loop(), tx_loop())

    except WebSocketDisconnect:
        print("Cliente WebSocket desconectado.")
    except Exception as e:
        print(f"Erro no WebSocket: {e}")
    finally:
        if sdr and rxStream:
            sdr.deactivateStream(rxStream)
            sdr.closeStream(rxStream)
            sdr_manager.active_stream = None
        sdr_manager.release_device()

if __name__ == "__main__":
    import uvicorn
    print("Iniciando o servidor web Uvicorn...")
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=False)