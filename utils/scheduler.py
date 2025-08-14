import time
import datetime
import json
import os
import threading
import tle
from skyfield.api import load, EarthSatellite, Topos, Loader
from utils.scanner import perform_capture
from utils.sdr_manager import sdr_manager
from utils.logger import logger
from utils import db

TLE_CACHE_DIR = "tle_cache"
os.makedirs(TLE_CACHE_DIR, exist_ok=True)

load_skyfield = Loader('~/.skyfield-data', verbose=False)

def cleanup_old_captures():
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
        if not os.path.isdir(captures_dir):
            return
        for filename in os.listdir(captures_dir):
            if not filename.endswith(".wav"):
                continue
            filepath = os.path.join(captures_dir, filename)
            file_mod_time = os.path.getmtime(filepath)
            if file_mod_time < cutoff_time:
                logger.log(f"Limpando captura antiga: {filename}", "INFO")
                os.remove(filepath)
                image_path = os.path.join(
                    images_dir, filename.replace(".wav", ".png")
                )
                if os.path.exists(image_path):
                    os.remove(image_path)
    except Exception as e:
        logger.log(f"Erro durante a limpeza de capturas antigas: {e}", "ERROR")

class Scheduler(threading.Thread):
    def __init__(self, scanner_event, shared_status):
        super().__init__()
        self.scanner_event = scanner_event
        self.shared_status = shared_status
        self.ts = load_skyfield.timescale()
        self._stop_event = threading.Event()
        self._is_capturing = threading.Event()
        self.daemon = True
        self.satellites = {}
        self.pass_predictions = {}

    def stop(self):
        self._stop_event.set()

    def is_idle(self):
        return not self._is_capturing.is_set()

    def _calculate_and_cache_passes(
        self, station, sat_name, sat_object, targets_config
    ):
        logger.log(f"Calculando passagens futuras para {sat_name}...", "DEBUG")
        now = self.ts.now()
        t1 = self.ts.utc(now.utc_datetime() + datetime.timedelta(days=2))
        
        times, events = sat_object.find_events(station, now, t1, altitude_degrees=10.0)
        
        future_passes = []
        target_info_base = next(
            (t for t in targets_config if t["name"] == sat_name), None
        )
        if not target_info_base:
            return
        for i in range(len(events) - 2):
            if events[i] == 0 and events[i + 1] == 1 and events[i + 2] == 2:
                start_time = times[i]
                end_time = times[i + 2]
                duration_seconds = (
                    end_time.utc_datetime() - start_time.utc_datetime()
                ).total_seconds()
                target_info_pass = target_info_base.copy()
                target_info_pass["capture_duration_seconds"] = int(duration_seconds)
                future_passes.append(
                    {
                        "name": sat_name,
                        "start": start_time,
                        "end": end_time,
                        "target_info": target_info_pass,
                    }
                )
        self.pass_predictions[sat_name] = future_passes
        logger.log(f"Encontradas {len(future_passes)} passagens para {sat_name}.", "DEBUG")

    def _get_next_imminent_pass_from_cache(self):
        all_imminent_passes = []
        now_utc = datetime.datetime.utcnow().replace(tzinfo=datetime.timezone.utc)
        for sat_name, passes in self.pass_predictions.items():
            valid_passes = [p for p in passes if p["start"].utc_datetime() > now_utc]
            if valid_passes:
                all_imminent_passes.append(valid_passes[0])
            self.pass_predictions[sat_name] = valid_passes
        if not all_imminent_passes:
            return None
        all_imminent_passes.sort(key=lambda p: p["start"].utc_datetime())
        return all_imminent_passes[0]

    def run(self):
        logger.log("Agendador iniciado.", "INFO")
        last_tle_update_time = 0
        last_cleanup_time = 0
        MIN_TLE_UPDATE_INTERVAL_SECONDS = 2 * 3600
        CHECK_INTERVAL_SECONDS = 15
        IDLE_INTERVAL_SECONDS = 300

        while not self._stop_event.is_set():
            try:
                self.scanner_event.wait()
                with open("config.json", "r") as f:
                    config = json.load(f)
                station_geo = Topos(
                    latitude_degrees=float(config["station"]["latitude"].split()[0]),
                    longitude_degrees=float(config["station"]["longitude"].split()[0]),
                    elevation_m=config["station"]["elevation_m"],
                )
                targets = config["targets"]
                now = time.time()
                if (now - last_cleanup_time) > 6 * 3600:
                    cleanup_old_captures()
                    last_cleanup_time = now

                recalculate_passes_needed = False
                time_since_last_update = now - last_tle_update_time

                if time_since_last_update > MIN_TLE_UPDATE_INTERVAL_SECONDS:
                    logger.log("Verificando necessidade de atualização de TLEs...", "INFO")
                    
                    unique_urls = {target['tle_url']: target['name'].split()[0] for target in targets}
                    tle_groups = {}
                    
                    for url, group_name in unique_urls.items():
                        cache_path = os.path.join(TLE_CACHE_DIR, f"{group_name}.txt")
                        
                        logger.log(f"Tentando baixar TLEs de {url}...", "INFO")
                        tle_data = tle.fetch_tle_from_url(url)
                        
                        if tle_data:
                            logger.log("Download de TLE bem-sucedido. Atualizando cache.", "SUCCESS")
                            with open(cache_path, "w") as f_cache:
                                f_cache.write(tle_data)
                            tle_groups[url] = tle_data
                        else:
                            logger.log(f"Falha no download de {url}. Usando cache, se disponível.", "WARN")
                            if os.path.exists(cache_path):
                                with open(cache_path, "r") as f_cache:
                                    tle_groups[url] = f_cache.read()

                    self.satellites.clear()
                    for target in targets:
                        group_text = tle_groups.get(target['tle_url'])
                        if group_text:
                            tle_lines = tle.extract_tle_from_group(group_text, target['name'])
                            if tle_lines:
                                self.satellites[target['name']] = EarthSatellite(
                                    tle_lines[1], tle_lines[2], target['name'], self.ts
                                )
                    
                    recalculate_passes_needed = True
                    last_tle_update_time = now

                if recalculate_passes_needed or not self.pass_predictions:
                    logger.log("Recalculando todas as previsões de passagem...", "INFO")
                    self.pass_predictions.clear()
                    for name, sat_obj in self.satellites.items():
                        self._calculate_and_cache_passes(station_geo, name, sat_obj, targets)

                sdr_dev = sdr_manager.find_hackrf()
                self.shared_status["hackrf_status"]["connected"] = bool(sdr_dev)
                self.shared_status["hackrf_status"][
                    "status_text"
                ] = "HackRF Conectado" if sdr_dev else "HackRF Desconectado"
                
                next_pass = self._get_next_imminent_pass_from_cache()

                if next_pass and sdr_dev:
                    self.shared_status["next_pass"] = {
                        "name": next_pass["name"],
                        "start_utc": next_pass["start"].utc_iso(),
                    }
                    wait_seconds = (
                        next_pass["start"].utc_datetime()
                        - datetime.datetime.utcnow().replace(
                            tzinfo=datetime.timezone.utc
                        )
                    ).total_seconds()
                    if 0 < wait_seconds <= 60:
                        self._is_capturing.set()
                        logger.log(
                            f"Captura iminente de {next_pass['name']}. Duração: {next_pass['target_info']['capture_duration_seconds']}s. Preparando...",
                            "WARN",
                        )
                        time.sleep(max(0, wait_seconds - 2))
                        perform_capture(None, next_pass["target_info"])
                        self._is_capturing.clear()
                        self.shared_status["next_pass"] = None
                        time.sleep(5)
                        continue
                    else:
                        time.sleep(CHECK_INTERVAL_SECONDS)
                else:
                    self.shared_status["next_pass"] = None
                    time.sleep(IDLE_INTERVAL_SECONDS)
            except Exception as e:
                logger.log(f"Erro inesperado no loop do agendador: {e}", "ERROR")
                time.sleep(60)