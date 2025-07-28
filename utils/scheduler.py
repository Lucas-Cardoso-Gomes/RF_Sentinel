# utils/scheduler.py
import time
import datetime
import json
import os
import threading
import tle
from skyfield.api import load, EarthSatellite, Topos
from utils.scanner import perform_capture
from utils.sdr_manager import sdr_manager
from utils.logger import logger
from utils import db # Importar db para a função de limpeza

def cleanup_old_captures():
    """Verifica e apaga capturas antigas com base no config.json."""
    try:
        with open("config.json", "r") as f:
            config = json.load(f)
        
        storage_config = config.get("storage_management", {})
        if not storage_config.get("auto_delete_enabled", False):
            return

        delete_after_days = storage_config.get("delete_after_days", 7)
        cutoff_time = time.time() - (delete_after_days * 86400)
        
        captures_dir = "captures"
        images_dir = os.path.join(captures_dir, "images")
        
        # Lista todos os arquivos .wav na pasta de capturas
        if not os.path.isdir(captures_dir):
            return
            
        for filename in os.listdir(captures_dir):
            if not filename.endswith(".wav"):
                continue

            filepath = os.path.join(captures_dir, filename)
            file_mod_time = os.path.getmtime(filepath)

            if file_mod_time < cutoff_time:
                logger.log(f"Limpando captura antiga: {filename}", "INFO")
                
                # Deleta o arquivo .wav
                os.remove(filepath)
                
                # Deleta a imagem .png correspondente, se existir
                image_path = os.path.join(images_dir, filename.replace(".wav", ".png"))
                if os.path.exists(image_path):
                    os.remove(image_path)
                    
                # Remove do banco de dados
                db.delete_signal_by_filepath(filepath)

    except Exception as e:
        logger.log(f"Erro durante a limpeza de capturas antigas: {e}", "ERROR")

class Scheduler(threading.Thread):
    def __init__(self, scanner_event, shared_status):
        super().__init__()
        self.scanner_event = scanner_event
        self.shared_status = shared_status
        self.ts = load.timescale()
        self._stop_event = threading.Event()
        self._is_capturing = threading.Event()
        self.daemon = True

    def stop(self):
        self._stop_event.set()

    def is_idle(self):
        return not self._is_capturing.is_set()

    def get_next_pass(self, station, satellite):
        now = self.ts.now()
        t1 = self.ts.utc(now.utc_datetime() + datetime.timedelta(days=2))
        times, events = satellite.find_events(station, now, t1, altitude_degrees=25.0)
        for i in range(len(events) - 2):
            if events[i] == 0 and events[i + 1] == 1 and events[i + 2] == 2:
                if times[i].utc_datetime() > datetime.datetime.utcnow().replace(tzinfo=datetime.timezone.utc):
                    return times[i], times[i+2]
        return None, None

    def run(self):
        logger.log("Agendador iniciado.", "INFO")
        last_tle_update = 0
        last_cleanup_time = 0

        while not self._stop_event.is_set():
            try:
                config = json.load(open("config.json", "r"))
                station_geo = Topos(latitude_degrees=float(config['station']['latitude'].split()[0]), longitude_degrees=float(config['station']['longitude'].split()[0]), elevation_m=config['station']['elevation_m'])
                targets = config['targets']
                satellites = {}

                # --- Executa a limpeza a cada 6 horas ---
                if (time.time() - last_cleanup_time) > 6 * 3600:
                    logger.log("Executando verificação de limpeza de armazenamento...", "INFO")
                    cleanup_old_captures()
                    last_cleanup_time = time.time()
                
                # --- Atualização de TLE a cada 6 horas ---
                if not satellites or (time.time() - last_tle_update) > 6 * 3600:
                    logger.log("Atualizando dados TLE...", "INFO")
                    # (Lógica de TLE permanece a mesma...)
                    tle_groups = {}
                    download_success = True
                    for target in targets:
                        url = target['tle_url']
                        if url not in tle_groups:
                            tle_data = tle.fetch_tle_from_url(url)
                            if tle_data:
                                tle_groups[url] = tle_data
                            else:
                                download_success = False; break
                    
                    if download_success:
                        for target in targets:
                            group_text = tle_groups.get(target['tle_url'])
                            if group_text:
                                tle_lines = tle.extract_tle_from_group(group_text, target['name'])
                                if tle_lines:
                                    satellites[target['name']] = EarthSatellite(tle_lines[1], tle_lines[2], tle_lines[0], self.ts)
                        logger.log(f"Dados TLE atualizados para {len(satellites)} satélite(s).", "SUCCESS")
                        last_tle_update = time.time()
                    else:
                        logger.log("Falha no download dos TLEs.", "WARN")

                sdr_dev = sdr_manager.find_hackrf()
                self.shared_status["hackrf_status"]["connected"] = bool(sdr_dev)
                self.shared_status["hackrf_status"]["status_text"] = "HackRF Conectado" if sdr_dev else "HackRF Desconectado"

                if not sdr_dev:
                    time.sleep(10); continue

                if not self.scanner_event.is_set():
                    if self.shared_status.get('next_pass') is not None:
                        self.shared_status['next_pass'] = None
                    time.sleep(5); continue

                # (O restante da lógica de agendamento de passagem permanece igual)
                all_future_passes = []
                if satellites:
                    for name, sat in satellites.items():
                        start, end = self.get_next_pass(station_geo, sat)
                        if start is not None:
                            all_future_passes.append({
                                "name": name, "start": start, "end": end,
                                "target_info": next((t for t in targets if t['name'] == name), None)
                            })
                    all_future_passes.sort(key=lambda p: p['start'].utc_datetime())

                if all_future_passes:
                    next_pass = all_future_passes[0]
                    self.shared_status['next_pass'] = {'name': next_pass['name'], 'start_utc': next_pass['start'].utc_iso()}
                    wait_seconds = (next_pass['start'].utc_datetime() - datetime.datetime.utcnow().replace(tzinfo=datetime.timezone.utc)).total_seconds()
                    
                    if wait_seconds <= 60 and wait_seconds > 0:
                        self._is_capturing.set()
                        logger.log(f"Captura iminente de {next_pass['name']}. Preparando...", "WARN")
                        if wait_seconds > 2: time.sleep(wait_seconds - 2)
                        
                        sdr = sdr_manager.acquire()
                        if sdr:
                            try:
                                perform_capture(sdr, next_pass['target_info'])
                            finally:
                                sdr_manager.release(sdr)
                        
                        self._is_capturing.clear()
                        self.shared_status['next_pass'] = None
                        time.sleep(10)
                    else:
                        logger.log(f"Aguardando passagem: {next_pass['name']} em {wait_seconds/60:.1f} min.", "INFO")
                        time.sleep(15)
                else:
                    self.shared_status['next_pass'] = None
                    logger.log("Nenhuma passagem futura encontrada. Verificando em 5 minutos.", "INFO")
                    time.sleep(300)

            except Exception as e:
                logger.log(f"Erro inesperado no loop do agendador: {e}", "ERROR")
                time.sleep(60)