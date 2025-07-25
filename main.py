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
from fastapi.staticfiles import StaticFiles

from fastapi import WebSocket, WebSocketDisconnect
import numpy as np
import SoapySDR
from SoapySDR import *
import asyncio

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

app.mount("/captures", StaticFiles(directory="captures"), name="captures")

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

@app.websocket("/ws/waterfall")
async def websocket_endpoint(websocket: WebSocket):
    await websocket.accept()
    print("Cliente WebSocket conectado para o waterfall.")

    sdr = None
    rxStream = None
    try:
        # Configuração do SDR para o waterfall
        sdr_devices = SoapySDR.Device.enumerate()
        if not sdr_devices:
            raise RuntimeError("Nenhum dispositivo SDR encontrado.")
        
        sdr = SoapySDR.Device(sdr_devices[0])
        sdr.setSampleRate(SOAPY_SDR_RX, 0, 2.4e6)
        sdr.setFrequency(SOAPY_SDR_RX, 0, 101.1e6) # Frequência central inicial (ex: rádio FM)
        sdr.setGain(SOAPY_SDR_RX, 0, 30)

        rxStream = sdr.setupStream(SOAPY_SDR_RX, SOAPY_SDR_CF32)
        sdr.activateStream(rxStream)
        
        # Tamanho do buffer para FFT
        fft_size = 1024
        samples = np.zeros(fft_size, np.complex64)

        while True:
            # Lê amostras do SDR
            sr = sdr.readStream(rxStream, [samples], len(samples))
            
            # Calcula a FFT e a magnitude em dB
            fft_result = np.fft.fftshift(np.fft.fft(samples))
            psd = np.abs(fft_result)**2
            psd_db = 10 * np.log10(psd / (fft_size**2))
            
            # Envia os dados para o cliente
            await websocket.send_json(psd_db.tolist())
            await asyncio.sleep(0.05) # Controla a taxa de atualização

    except WebSocketDisconnect:
        print("Cliente WebSocket desconectado.")
    except Exception as e:
        print(f"Erro no WebSocket: {e}")
        await websocket.close(code=1011, reason=str(e))
    finally:
        # Garante que o stream seja fechado
        if sdr and rxStream:
            print("Desativando stream do SDR.")
            sdr.deactivateStream(rxStream)
            sdr.closeStream(rxStream)

if __name__ == "__main__":
    import uvicorn
    print("Iniciando o servidor web Uvicorn...")
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=False)