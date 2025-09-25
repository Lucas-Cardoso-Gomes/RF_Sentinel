from fastapi import FastAPI, Request
from fastapi.concurrency import run_in_threadpool
from fastapi.responses import HTMLResponse, JSONResponse, FileResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
import os
import threading

from utils import db
from utils.analyzer import analyze_wav_file
from fastapi import WebSocket, WebSocketDisconnect
from utils.scanner import perform_capture
from utils.scheduler import Scheduler
from utils.state_manager import AppState
from utils.wifi_analyzer import run_wifi_scan
import asyncio

app = FastAPI(title="RFSentinel")

@app.on_event("startup")
async def startup_event():
    # Cria uma instância única do gerenciador de estado e a anexa ao estado do app.
    app_state = AppState()
    app.state.app_state = app_state

    app_state.log("Evento de startup: a iniciar tarefas de fundo...", "INFO")
    db.init_db()

    # O Scheduler agora recebe a instância do AppState para gerenciar o estado de forma centralizada.
    scheduler_thread = Scheduler(app_state)
    scheduler_thread.start()
    app_state.scheduler_thread = scheduler_thread

@app.on_event("shutdown")
async def shutdown_event():
    app_state = app.state.app_state
    app_state.log("Evento de shutdown: a encerrar tarefas de fundo...", "WARN")

    if app_state.scheduler_thread and app_state.scheduler_thread.is_alive():
        app_state.scheduler_thread.stop()
        app_state.scheduler_thread.join(timeout=5)
        app_state.log("Thread do agendador parada com sucesso.", "SUCCESS")

app.mount("/static", StaticFiles(directory="static"), name="static")
templates = Jinja2Templates(directory="templates")

def run_manual_capture(app_state: AppState, target_info: dict):
    """Função executada em uma thread para a captura manual."""
    app_state.status["manual_capture_active"] = True
    app_state.log("Iniciando captura manual...", "WARN")
    try:
        # A função perform_capture agora também precisa do app_state.
        perform_capture(app_state, None, target_info)
    except Exception as e:
        app_state.log(f"Erro na thread de captura manual: {e}", "ERROR")
    finally:
        app_state.log("Captura manual finalizada.", "SUCCESS")
        app_state.status["manual_capture_active"] = False
        # O lock é liberado aqui, garantindo que ele seja liberado mesmo se a captura falhar.
        if app_state.capture_lock.locked():
            app_state.capture_lock.release()

@app.get("/", response_class=HTMLResponse)
async def read_root(request: Request):
    return templates.TemplateResponse("index.html", {"request": request})

@app.get("/wifi-analyzer", response_class=HTMLResponse)
async def wifi_analyzer_page(request: Request):
    """Serve a página do analisador de espectro Wi-Fi."""
    return templates.TemplateResponse("wifi_analyzer.html", {"request": request})

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
    app_state: AppState = request.app.state.app_state

    if not app_state.capture_lock.acquire(blocking=False):
        return JSONResponse(
            content={"error": "Outra captura já está em andamento."}, 
            status_code=409
        )

    try:
        data = await request.json()
        capture_name = data.get("name", "").strip()
        if not capture_name:
            mode = data.get("mode", "RAW")
            freq_mhz = float(data.get("frequency_mhz", 0))
            capture_name = f"Manual_{mode}_{freq_mhz:.3f}MHz"

        sample_rate = int(data.get("sample_rate", 2e6))
        if sample_rate < 2e6:
            app_state.log(f"Taxa de amostragem de {sample_rate}Hz é inválida. A reverter para o mínimo de 2MHz.", "WARN")
            sample_rate = 2000000

        target_info = {
            "name": capture_name,
            "frequency": int(float(data.get("frequency_mhz", 0)) * 1e6),
            "capture_duration_seconds": int(data.get("duration_sec", 10)),
            "sample_rate": sample_rate,
            "mode": data.get("mode", "RAW"),
            "lna_gain": int(data.get("lna_gain", 40)),
            "vga_gain": int(data.get("vga_gain", 30)),
            "amp_enabled": bool(data.get("amp_enabled", True)),
            "force_decode": bool(data.get("force_decode", False))
        }
        
        decoder_type = data.get("decoder_type", "none")
        if decoder_type != "none":
            target_info['type'] = decoder_type
            app_state.log(f"Decodificador '{decoder_type}' selecionado para captura manual.", "INFO")
            if target_info['force_decode']:
                app_state.log("Opção 'Forçar Decodificação' está ativa.", "WARN")

        # A thread agora recebe o app_state para ter acesso seguro ao estado.
        thread = threading.Thread(target=run_manual_capture, args=(app_state, target_info))
        thread.start()

        return JSONResponse(content={"status": "Captura manual iniciada."}, status_code=202)
        
    except Exception as e:
        # Se a thread não for iniciada, o lock deve ser liberado aqui.
        if app_state.capture_lock.locked():
            app_state.capture_lock.release()
        app_state.log(f"Erro ao iniciar captura manual: {e}", "ERROR")
        return JSONResponse(content={"error": "Falha interna ao iniciar captura."}, status_code=500)

@app.get("/api/status")
def get_status(request: Request):
    app_state: AppState = request.app.state.app_state
    scheduler = app_state.scheduler_thread

    if not scheduler:
        return JSONResponse(content={"error": "O agendador não foi inicializado."}, status_code=503)

    return { 
        "scanner_status": "Ativo" if app_state.scanner_event.is_set() else "Pausado",
        "hackrf_status": app_state.status["hackrf_status"],
        "next_pass": app_state.status["next_pass"],
        "scheduler_log": app_state.get_logs(),
        "manual_capture_active": app_state.status["manual_capture_active"],
        "is_scheduler_capturing": not scheduler.is_idle() 
    }

@app.get("/api/passes")
def get_upcoming_passes(request: Request):
    app_state: AppState = request.app.state.app_state
    scheduler = app_state.scheduler_thread
    all_passes = []

    if scheduler:
        with scheduler.predictions_lock:
            # Copia os dados para evitar manter o lock durante o processamento.
            pass_predictions_copy = dict(scheduler.pass_predictions)

        for sat_passes in pass_predictions_copy.values():
            for p in sat_passes:
                all_passes.append({
                    "name": p["name"],
                    "start_utc": p["start"].utc_iso(),
                    "end_utc": p["end"].utc_iso()
                })

    all_passes.sort(key=lambda x: x["start_utc"])
    return all_passes

@app.get("/api/signals")
async def get_signals():
    return await run_in_threadpool(db.get_latest_signals, 15)

@app.get("/api/signal/info/{signal_id}")
async def get_signal_info(signal_id: int):
    def _get_info_sync():
        conn = db.get_db_connection()
        try:
            signal = conn.execute("SELECT * FROM signals WHERE id = ?", (signal_id,)).fetchone()
            return dict(signal) if signal else None
        finally:
            conn.close()

    signal_data = await run_in_threadpool(_get_info_sync)
    if signal_data:
        return signal_data
    return JSONResponse(content={"error": "Sinal não encontrado"}, status_code=404)

@app.get("/api/signal/analyze/{signal_id}")
async def analyze_signal(signal_id: int):
    def _get_and_analyze_sync():
        conn = db.get_db_connection()
        try:
            signal = conn.execute("SELECT filepath FROM signals WHERE id = ?", (signal_id,)).fetchone()
        finally:
            conn.close()

        if not signal or not signal['filepath'] or not os.path.exists(signal['filepath']) or '_RAW' not in signal['filepath']:
            return None, "Ficheiro não encontrado ou não é do tipo RAW."

        analysis_data = analyze_wav_file(signal['filepath'])
        if analysis_data:
            return analysis_data, None
        return None, "Falha ao processar ficheiro."

    analysis_data, error_msg = await run_in_threadpool(_get_and_analyze_sync)
    
    if error_msg:
        status_code = 404 if "não encontrado" in error_msg else 500
        return JSONResponse(content={"error": error_msg}, status_code=status_code)
    return analysis_data

@app.post("/scanner/toggle")
async def toggle_scanner(request: Request):
    app_state: AppState = request.app.state.app_state

    if app_state.scanner_event.is_set():
        app_state.scanner_event.clear()
        app_state.log("Scanner de satélites pausado pelo usuário.", "WARN")
    else:
        app_state.scanner_event.set()
        app_state.log("Scanner de satélites ativado pelo usuário.", "INFO")

    return {"status": "Ativo" if app_state.scanner_event.is_set() else "Pausado"}

@app.delete("/api/signal/delete/{signal_id}")
async def delete_signal(signal_id: int, request: Request):
    app_state: AppState = request.app.state.app_state
    app_state.log(f"Recebida solicitação para apagar sinal ID: {signal_id}", "INFO")

    def _delete_sync():
        paths = db.get_signal_paths_by_id(signal_id)
        if not paths:
            return {"error": "Sinal não encontrado no banco de dados.", "status_code": 404}

        # Apaga o arquivo de áudio se existir
        if paths.get("filepath") and os.path.exists(paths["filepath"]):
            try:
                os.remove(paths["filepath"])
                app_state.log(f"Ficheiro .wav apagado: {paths['filepath']}", "SUCCESS")
            except OSError as e:
                app_state.log(f"Erro ao apagar ficheiro .wav {paths['filepath']}: {e}", "ERROR")

        # Apaga o arquivo de imagem se existir
        if paths.get("image_path") and os.path.exists(paths["image_path"]):
            try:
                os.remove(paths["image_path"])
                app_state.log(f"Ficheiro de imagem apagado: {paths['image_path']}", "SUCCESS")
            except OSError as e:
                app_state.log(f"Erro ao apagar ficheiro de imagem {paths['image_path']}: {e}", "ERROR")

        # Apaga o registro do banco de dados
        if db.delete_signal_by_id(signal_id):
            return {"status": "Sinal e ficheiros associados apagados com sucesso."}

        return {"error": "Falha ao apagar registo do banco de dados.", "status_code": 500}

    result = await run_in_threadpool(_delete_sync)
    
    status_code = result.get("status_code", 200)
    if "error" in result:
        return JSONResponse(content={"error": result["error"]}, status_code=status_code)

    return JSONResponse(content={"status": result["status"]}, status_code=status_code)

@app.websocket("/ws/wifi_scan/{band}")
async def websocket_wifi_scan(websocket: WebSocket, band: str):
    """
    Endpoint WebSocket para transmitir dados da varredura de espectro Wi-Fi.
    """
    await websocket.accept()
    app_state: AppState = websocket.app.state.app_state
    
    # Cria uma tarefa para a varredura, permitindo que seja cancelada na desconexão.
    scan_task = asyncio.create_task(
        _wifi_scan_publisher(websocket, band, app_state)
    )

    try:
        # Mantém a conexão aberta, aguardando a desconexão do cliente.
        while True:
            await websocket.receive_text()
    except WebSocketDisconnect:
        app_state.log(f"Cliente WebSocket desconectado da varredura da banda {band}.", "INFO")
    finally:
        # Cancela a tarefa de varredura quando o cliente se desconecta.
        scan_task.cancel()
        # Aguarda a tarefa ser devidamente cancelada.
        await asyncio.gather(scan_task, return_exceptions=True)

async def _wifi_scan_publisher(websocket: WebSocket, band: str, app_state: AppState):
    """
    Função auxiliar que executa a varredura e envia os dados pelo WebSocket.
    """
    try:
        async for data_point in run_wifi_scan(band, app_state):
            await websocket.send_json(data_point)
    except asyncio.CancelledError:
        # Esta exceção é esperada quando a tarefa é cancelada.
        app_state.log("Tarefa de publicação da varredura foi cancelada.", "DEBUG")
    except Exception as e:
        app_state.log(f"Erro inesperado no publicador da varredura: {e}", "ERROR")
        # Tenta enviar uma mensagem de erro ao cliente antes de fechar.
        try:
            await websocket.send_json({"error": "Ocorreu um erro inesperado no servidor."})
        except Exception:
            pass # A conexão pode já estar fechada.