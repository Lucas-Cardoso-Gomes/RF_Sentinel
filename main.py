# main.py
import sys
import os
import threading
import json
import time
import asyncio

# Silencia os logs do libusb, deve ser uma das primeiras linhas
os.environ['LIBUSB_DEBUG'] = '0'

sys.path.insert(0, os.path.abspath(os.path.dirname(__file__)))

from utils.win_dll_fix import apply as apply_win_dll_fix
apply_win_dll_fix() 

from fastapi import FastAPI, Request, WebSocket, WebSocketDisconnect
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

import numpy as np
import SoapySDR
from SoapySDR import *

from utils import db
from utils.scheduler import Scheduler
from utils.scanner import perform_capture
from utils.sdr_manager import sdr_manager
from utils.analyzer import analyze_wav_file
from utils.logger import logger # Importa a instância pronta do logger

# --- Estado compartilhado e eventos ---
SHARED_STATUS = {
    "hackrf_status": {"connected": False, "status_text": "Verificando..."},
    "next_pass": None,
    "scheduler_log": logger.shared_log, # A lista de logs agora vem diretamente do logger
    "manual_capture_active": False
}
waterfall_event = threading.Event(); waterfall_event.set()
scanner_event = threading.Event(); scanner_event.set()
db.init_db()

# --- Inicialização do Scheduler ---
scheduler_thread = Scheduler(scanner_event, SHARED_STATUS, waterfall_event)
scheduler_thread.start()

# --- Configuração do FastAPI ---
app = FastAPI(title="RFSentinel")
app.mount("/captures", StaticFiles(directory="captures"), name="captures")
templates = Jinja2Templates(directory="templates")

def run_manual_capture(target_info):
    """Função em thread para captura manual com controle de prioridade."""
    SHARED_STATUS["manual_capture_active"] = True
    waterfall_event.clear()
    logger.log("Pausando waterfall para captura manual...", "WARN")
    time.sleep(2)
    
    sdr = sdr_manager.acquire()
    if sdr:
        try:
            perform_capture(sdr, target_info)
        finally:
            sdr_manager.release(sdr)
    
    logger.log("Captura manual finalizada.", "SUCCESS")
    waterfall_event.set()
    SHARED_STATUS["manual_capture_active"] = False

# --- Endpoints da API e da Interface ---

@app.get("/", response_class=HTMLResponse)
async def read_root(request: Request):
    """Serve a página principal do dashboard."""
    return templates.TemplateResponse("index.html", {"request": request})

@app.get("/analysis", response_class=HTMLResponse)
async def analysis_page(request: Request):
    """Serve a página de análise de sinal."""
    return templates.TemplateResponse("analysis.html", {"request": request})

@app.post("/api/capture/manual")
async def manual_capture_endpoint(request: Request):
    if SHARED_STATUS["manual_capture_active"] or not waterfall_event.is_set():
        return JSONResponse(content={"error": "Outra captura (manual ou agendada) já está em andamento."}, status_code=409)
    
    data = await request.json()
    target_info = {
        "name": data.get("name", "ManualCapture"),
        "frequency": int(float(data.get("frequency_mhz", 0)) * 1e6),
        "capture_duration_seconds": int(data.get("duration_sec", 10)),
        "gains": {"lna": 32, "vga": 20, "amp": 0}
    }
    threading.Thread(target=run_manual_capture, args=(target_info,)).start()
    return {"status": "Captura manual iniciada."}

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

@app.get("/api/signal/info/{signal_id}")
def get_signal_info(signal_id: int):
    conn = db.get_db_connection()
    signal = conn.execute("SELECT * FROM signals WHERE id = ?", (signal_id,)).fetchone()
    conn.close()
    return dict(signal) if signal else JSONResponse(content={"error": "Sinal não encontrado"}, status_code=404)

@app.get("/api/signal/analyze/{signal_id}")
def analyze_signal(signal_id: int):
    conn = db.get_db_connection()
    signal = conn.execute("SELECT filepath FROM signals WHERE id = ?", (signal_id,)).fetchone()
    conn.close()
    if not signal or not signal['filepath'] or not os.path.exists(signal['filepath']):
        return JSONResponse(content={"error": "Arquivo não encontrado."}, status_code=404)
    
    analysis_data = analyze_wav_file(signal['filepath'])
    return analysis_data if analysis_data else JSONResponse(content={"error": "Falha ao processar arquivo."}, status_code=500)

@app.post("/scanner/toggle")
def toggle_scanner():
    """Ativa ou desativa o agendador de satélites."""
    if scanner_event.is_set(): scanner_event.clear()
    else: scanner_event.set()
    return {"status": "Ativo" if scanner_event.is_set() else "Parado"}

@app.websocket("/ws/waterfall")
async def websocket_endpoint(websocket: WebSocket):
    """Endpoint WebSocket para o waterfall interativo."""
    await websocket.accept()
    if not waterfall_event.is_set():
        await websocket.close(code=1011, reason="SDR em uso para uma captura prioritária.")
        return

    sdr = sdr_manager.acquire()
    if not sdr:
        await websocket.close(code=1011, reason="Não foi possível adquirir o dispositivo SDR.")
        return
    
    rxStream = None
    try:
        sample_rate = 2.4e6
        center_freq = 101.1e6
        gain = 32
        
        sdr.setSampleRate(SOAPY_SDR_RX, 0, sample_rate)
        sdr.setFrequency(SOAPY_SDR_RX, 0, center_freq)
        sdr.setGain(SOAPY_SDR_RX, 0, gain)

        await websocket.send_json({"type": "metadata", "sample_rate": sample_rate, "center_freq": center_freq})

        rxStream = sdr.setupStream(SOAPY_SDR_RX, SOAPY_SDR_CF32)
        sdr.activateStream(rxStream)
        
        fft_size = 1024
        samples = np.zeros(fft_size, np.complex64)

        async def rx_loop():
            while True:
                if not waterfall_event.is_set():
                    await websocket.close(code=1012, reason="SDR requisitado para captura.")
                    break
                
                sr = sdr.readStream(rxStream, [samples], len(samples), timeoutUs=100000)
                if sr.ret > 0:
                    fft_result = np.fft.fftshift(np.fft.fft(samples))
                    psd = np.abs(fft_result)**2
                    psd_db = 10 * np.log10(psd / (fft_size**2) + 1e-12)
                    await websocket.send_json({"type": "fft_data", "data": psd_db.tolist()})
                
                await asyncio.sleep(0.05)

        async def tx_loop():
            while True:
                message = await websocket.receive_text()
                data = json.loads(message)
                if 'frequency' in data:
                    new_freq = float(data['frequency'])
                    sdr.setFrequency(SOAPY_SDR_RX, 0, new_freq)
                    await websocket.send_json({"type": "metadata", "center_freq": new_freq})
                if 'gain' in data:
                    sdr.setGain(SOAPY_SDR_RX, 0, int(data['gain']))
        
        await asyncio.gather(rx_loop(), tx_loop())

    except WebSocketDisconnect:
        logger.log("Cliente WebSocket desconectado.", "INFO")
    except Exception as e:
        logger.log(f"Erro no WebSocket: {e}", "ERROR")
    finally:
        if sdr and rxStream: 
            sdr.deactivateStream(rxStream)
            sdr.closeStream(rxStream)
        sdr_manager.release(sdr)

if __name__ == "__main__":
    import uvicorn
    logger.log("Iniciando o servidor web Uvicorn...", "INFO")
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=False)