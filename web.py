from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse, JSONResponse, FileResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
import os
import threading

from utils import db
from utils.analyzer import analyze_wav_file
from utils.logger import logger
from utils.scanner import perform_capture
from app_state import SHARED_STATUS, scanner_event, scheduler_thread, capture_lock

app = FastAPI(title="RFSentinel")

app.mount("/static", StaticFiles(directory="static"), name="static")
templates = Jinja2Templates(directory="templates")

def run_manual_capture(target_info):
    """Função executada em uma thread para captura manual."""
    SHARED_STATUS["manual_capture_active"] = True
    logger.log("Iniciando captura manual por streaming...", "WARN")
    try:
        perform_capture(None, target_info)
    except Exception as e:
        logger.log(f"Erro não esperado na thread de captura manual: {e}", "ERROR")
    finally:
        logger.log("Captura manual finalizada.", "SUCCESS")
        SHARED_STATUS["manual_capture_active"] = False
        capture_lock.release() # Garante que o lock é libertado no final

@app.get("/", response_class=HTMLResponse)
async def read_root(request: Request):
    return templates.TemplateResponse("index.html", {"request": request})

@app.get("/analysis", response_class=HTMLResponse)
async def analysis_page(request: Request):
    return templates.TemplateResponse("analysis.html", {"request": request})

@app.get("/captures/{filepath:path}")
def serve_capture_file(filepath: str):
    full_path = os.path.join("captures", filepath)
    if os.path.exists(full_path):
        return FileResponse(full_path)
    return JSONResponse(content={"error": "Ficheiro não encontrado"}, status_code=404)

@app.post("/api/capture/manual")
async def manual_capture_endpoint(request: Request):
    # Tenta adquirir o lock de forma não-bloqueante.
    # Se já estiver bloqueado, significa que outra captura está ativa.
    if not capture_lock.acquire(blocking=False):
        return JSONResponse(
            content={"error": "Outra captura já está em andamento."}, 
            status_code=409 # Código de Conflito
        )

    # Se chegámos aqui, o lock foi adquirido com sucesso.
    try:
        data = await request.json()
        
        capture_name = data.get("name")
        if not capture_name or not capture_name.strip():
            mode = data.get("mode", "RAW")
            freq_mhz = float(data.get("frequency_mhz", 0))
            capture_name = f"Manual_{mode}_{freq_mhz:.3f}MHz"
        
        sample_rate = data.get("sample_rate", 2e6)
        if sample_rate < 2e6:
            sample_rate = 2e6

        target_info = {
            "name": capture_name,
            "frequency": int(float(data.get("frequency_mhz", 0)) * 1e6),
            "capture_duration_seconds": int(data.get("duration_sec", 10)),
            "sample_rate": sample_rate,
            "mode": data.get("mode", "RAW"),
            "lna_gain": data.get("lna_gain", 40),
            "vga_gain": data.get("vga_gain", 30),
            "amp_enabled": data.get("amp_enabled", True)
        }
        
        # Iniciar a thread que fará o trabalho e libertará o lock no final
        threading.Thread(target=run_manual_capture, args=(target_info,)).start()
        return {"status": "Captura manual iniciada."}
        
    except Exception as e:
        # Caso ocorra um erro antes de a thread iniciar, liberta o lock
        capture_lock.release()
        logger.log(f"Erro ao iniciar captura manual: {e}", "ERROR")
        return JSONResponse(content={"error": "Falha interna ao iniciar captura."}, status_code=500)


@app.get("/api/status")
def get_status():
    if not scheduler_thread:
        return {"error": "Scheduler not initialized"}
    return { 
        "scanner_status": "Ativo" if scanner_event.is_set() else "Pausado", 
        "hackrf_status": SHARED_STATUS["hackrf_status"], 
        "next_pass": SHARED_STATUS["next_pass"], 
        "scheduler_log": SHARED_STATUS["scheduler_log"], 
        "manual_capture_active": SHARED_STATUS["manual_capture_active"], 
        "is_scheduler_capturing": not scheduler_thread.is_idle() 
    }

@app.get("/api/passes")
def get_upcoming_passes():
    all_passes = []
    if scheduler_thread and scheduler_thread.pass_predictions:
        for sat_passes in scheduler_thread.pass_predictions.values():
            for p in sat_passes:
                all_passes.append({
                    "name": p["name"],
                    "start_utc": p["start"].utc_iso(),
                    "end_utc": p["end"].utc_iso()
                })
    all_passes.sort(key=lambda x: x["start_utc"])
    return all_passes

@app.get("/api/signals")
def get_signals():
    return db.get_latest_signals(15)

@app.get("/api/signal/info/{signal_id}")
def get_signal_info(signal_id: int):
    conn = db.get_db_connection()
    signal = conn.execute("SELECT * FROM signals WHERE id = ?", (signal_id,)).fetchone()
    conn.close()
    if signal:
        return dict(signal)
    return JSONResponse(content={"error": "Sinal não encontrado"}, status_code=404)

@app.get("/api/signal/analyze/{signal_id}")
def analyze_signal(signal_id: int):
    conn = db.get_db_connection()
    signal = conn.execute("SELECT filepath FROM signals WHERE id = ?", (signal_id,)).fetchone()
    conn.close()
    
    if not signal or not signal['filepath'] or not os.path.exists(signal['filepath']) or '_RAW' not in signal['filepath']:
        return JSONResponse(content={"error": "Ficheiro não encontrado ou não é do tipo RAW."}, status_code=404)
    
    analysis_data = analyze_wav_file(signal['filepath'])
    if analysis_data:
        return analysis_data
    return JSONResponse(content={"error": "Falha ao processar ficheiro."}, status_code=500)

@app.post("/scanner/toggle")
def toggle_scanner():
    if scanner_event.is_set():
        scanner_event.clear()
        logger.log("Scanner de satélites pausado pelo usuário.", "WARN")
    else:
        scanner_event.set()
        logger.log("Scanner de satélites ativado pelo usuário.", "INFO")
    return {"status": "Ativo" if scanner_event.is_set() else "Pausado"}

@app.delete("/api/signal/delete/{signal_id}")
def delete_signal(signal_id: int):
    logger.log(f"Recebida solicitação para apagar sinal ID: {signal_id}", "INFO")
    paths = db.get_signal_paths_by_id(signal_id)
    
    if not paths:
        return JSONResponse(content={"error": "Sinal não encontrado no banco de dados."}, status_code=404)
    
    if paths.get("filepath") and os.path.exists(paths["filepath"]):
        try:
            os.remove(paths["filepath"])
            logger.log(f"Ficheiro .wav apagado: {paths['filepath']}", "SUCCESS")
        except OSError as e:
            logger.log(f"Erro ao apagar ficheiro .wav {paths['filepath']}: {e}", "ERROR")
            
    if paths.get("image_path") and os.path.exists(paths["image_path"]):
        try:
            os.remove(paths["image_path"])
            logger.log(f"Ficheiro de imagem apagado: {paths['image_path']}", "SUCCESS")
        except OSError as e:
            logger.log(f"Erro ao apagar ficheiro de imagem {paths['image_path']}: {e}", "ERROR")
            
    if db.delete_signal_by_id(signal_id):
        return {"status": "Sinal e ficheiros apagados com sucesso."}
    
    return JSONResponse(content={"error": "Falha ao apagar registo do banco de dados."}, status_code=500)