import time
import datetime
import json
import os
import threading
import tle
from skyfield.api import load, EarthSatellite, Topos, Loader
from utils.scanner import perform_capture
from utils.sdr_manager import sdr_manager
from utils import db
from .state_manager import AppState

TLE_CACHE_DIR = "tle_cache"
os.makedirs(TLE_CACHE_DIR, exist_ok=True)

load_skyfield = Loader('~/.skyfield-data', verbose=False)

def cleanup_old_captures(app_state: AppState):
    """Realiza a limpeza de capturas e imagens antigas com base na configuração."""
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
            if not filename.endswith((".wav", ".raw")):
                continue

            filepath = os.path.join(captures_dir, filename)
            try:
                file_mod_time = os.path.getmtime(filepath)
                if file_mod_time < cutoff_time:
                    app_state.log(f"Limpando captura antiga: {filename}", "INFO")
                    os.remove(filepath)

                    # Tenta remover a imagem correspondente
                    image_filename = filename.rsplit('.', 1)[0] + ".png"
                    image_path = os.path.join(images_dir, image_filename)
                    if os.path.exists(image_path):
                        os.remove(image_path)
            except OSError as e:
                app_state.log(f"Erro ao processar o arquivo {filepath} para limpeza: {e}", "ERROR")

    except Exception as e:
        app_state.log(f"Erro durante a limpeza de capturas antigas: {e}", "ERROR")


class Scheduler(threading.Thread):
    def __init__(self, app_state: AppState):
        super().__init__()
        self.app_state = app_state
        self.ts = load_skyfield.timescale()
        self._stop_event = threading.Event()
        self._is_capturing = threading.Event()
        self.predictions_lock = threading.Lock()
        self.daemon = True
        self.satellites = {}
        self.pass_predictions = {}

    def stop(self):
        self._stop_event.set()

    def is_idle(self):
        return not self._is_capturing.is_set()

    def _calculate_and_cache_passes(self, station: Topos, sat_name: str, sat_object: EarthSatellite, targets_config: list):
        """Calcula e armazena em cache as passagens futuras de um satélite."""
        self.app_state.log(f"Calculando passagens futuras para {sat_name}...", "DEBUG")
        now = self.ts.now()
        # Calcula para as próximas 48 horas.
        t1 = self.ts.utc(now.utc_datetime() + datetime.timedelta(days=2))
        
        try:
            times, events = sat_object.find_events(station, now, t1, altitude_degrees=10.0)
        except Exception as e:
            self.app_state.log(f"Não foi possível calcular as passagens para {sat_name}: {e}", "ERROR")
            return

        future_passes = []
        target_info_base = next((t for t in targets_config if t["name"] == sat_name), None)
        if not target_info_base:
            return

        # O padrão de eventos para uma passagem completa é: 0 (nasce), 1 (culmina), 2 (se põe).
        for i, event in enumerate(events):
            if event == 0 and i + 2 < len(events) and events[i+1] == 1 and events[i+2] == 2:
                start_time = times[i]
                end_time = times[i + 2]
                duration = (end_time.utc_datetime() - start_time.utc_datetime()).total_seconds()

                pass_info = {
                    "name": sat_name,
                    "start": start_time,
                    "end": end_time,
                    "target_info": {**target_info_base, "capture_duration_seconds": int(duration)}
                }
                future_passes.append(pass_info)

        with self.predictions_lock:
            self.pass_predictions[sat_name] = future_passes

        self.app_state.log(f"Encontradas {len(future_passes)} passagens para {sat_name}.", "DEBUG")

    def _get_next_imminent_pass_from_cache(self):
        all_imminent_passes = []
        now_utc = datetime.datetime.utcnow().replace(tzinfo=datetime.timezone.utc)
        with self.predictions_lock:
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
        self.app_state.log("Agendador iniciado.", "INFO")
        last_tle_update_time = 0
        last_cleanup_time = 0
        MIN_TLE_UPDATE_INTERVAL_SECONDS = 2 * 3600  # 2 horas
        CHECK_INTERVAL_SECONDS = 15
        IDLE_INTERVAL_SECONDS = 300

        while not self._stop_event.is_set():
            try:
                # Aguarda o evento do scanner estar ativo, com um timeout para verificar periodicamente o _stop_event.
                if not self.app_state.scanner_event.wait(timeout=5):
                    continue

                with open("config.json", "r") as f:
                    config = json.load(f)

                station_geo = Topos(
                    latitude_degrees=float(config["station"]["latitude"].split()[0]),
                    longitude_degrees=float(config["station"]["longitude"].split()[0]),
                    elevation_m=config["station"]["elevation_m"],
                )
                targets = config["targets"]
                now = time.time()

                if (now - last_cleanup_time) > 6 * 3600: # Limpeza a cada 6 horas
                    cleanup_old_captures(self.app_state)
                    last_cleanup_time = now

                if (now - last_tle_update_time) > MIN_TLE_UPDATE_INTERVAL_SECONDS:
                    self.app_state.log("Verificando necessidade de atualização de TLEs...", "INFO")
                    self._update_tles_and_satellites(targets)
                    self._recalculate_all_passes(station_geo, targets)
                    last_tle_update_time = now

                sdr_dev = sdr_manager.find_hackrf()
                self.app_state.status["hackrf_status"]["connected"] = bool(sdr_dev)
                self.app_state.status["hackrf_status"]["status_text"] = "HackRF Conectado" if sdr_dev else "HackRF Desconectado"
                
                next_pass = self._get_next_imminent_pass_from_cache()

                if next_pass and sdr_dev:
                    self.app_state.status["next_pass"] = {
                        "name": next_pass["name"],
                        "start_utc": next_pass["start"].utc_iso(),
                    }
                    wait_seconds = (next_pass["start"].utc_datetime() - datetime.datetime.utcnow().replace(tzinfo=datetime.timezone.utc)).total_seconds()

                    if 0 < wait_seconds <= 60: # Se a passagem é no próximo minuto
                        if not self.app_state.capture_lock.acquire(blocking=False):
                            self.app_state.log(f"Ignorando passagem de {next_pass['name']}, pois outra captura está em andamento.", "WARN")
                            self._remove_pass_from_cache(next_pass['name'])
                            time.sleep(CHECK_INTERVAL_SECONDS)
                            continue
                        
                        try:
                            self._is_capturing.set()
                            self.app_state.log(f"Captura iminente de {next_pass['name']}. Duração: {next_pass['target_info']['capture_duration_seconds']}s.", "WARN")
                            time.sleep(max(0, wait_seconds - 2)) # Espera até 2s antes da passagem

                            perform_capture(self.app_state, None, next_pass["target_info"])
                        
                        finally:
                            self._is_capturing.clear()
                            self.app_state.status["next_pass"] = None
                            self.app_state.capture_lock.release()
                            time.sleep(5) # Pequeno delay para evitar loops rápidos
                    else:
                        time.sleep(CHECK_INTERVAL_SECONDS)
                else:
                    self.app_state.status["next_pass"] = None
                    time.sleep(IDLE_INTERVAL_SECONDS) # Se não há passagens, espera mais tempo

            except FileNotFoundError:
                self.app_state.log("Erro: 'config.json' não encontrado. Verifique a configuração.", "ERROR")
                time.sleep(60)
            except Exception as e:
                self.app_state.log(f"Erro inesperado no loop do agendador: {e}", "ERROR")
                time.sleep(60)

    def _update_tles_and_satellites(self, targets: list):
        """Baixa TLEs e atualiza os objetos de satélite."""
        self.app_state.log("Atualizando TLEs...", "INFO")
        unique_urls = {target['tle_url']: target['name'].split()[0] for target in targets}
        tle_groups = {}

        for url, group_name in unique_urls.items():
            cache_path = os.path.join(TLE_CACHE_DIR, f"{group_name}.txt")
            tle_data = tle.fetch_tle_from_url(url)
            if tle_data:
                self.app_state.log(f"TLE de {url} baixado com sucesso.", "SUCCESS")
                with open(cache_path, "w") as f_cache: f_cache.write(tle_data)
                tle_groups[url] = tle_data
            else:
                self.app_state.log(f"Falha ao baixar TLE de {url}. Usando cache se disponível.", "WARN")
                if os.path.exists(cache_path):
                    with open(cache_path, "r") as f_cache: tle_groups[url] = f_cache.read()

        self.satellites.clear()
        for target in targets:
            group_text = tle_groups.get(target['tle_url'])
            if group_text:
                tle_lines = tle.extract_tle_from_group(group_text, target['name'])
                if tle_lines:
                    self.satellites[target['name']] = EarthSatellite(tle_lines[1], tle_lines[2], target['name'], self.ts)

    def _recalculate_all_passes(self, station: Topos, targets: list):
        """Limpa e recalcula todas as previsões de passagem."""
        self.app_state.log("Recalculando todas as previsões de passagem...", "INFO")
        with self.predictions_lock:
            self.pass_predictions.clear()
        for name, sat_obj in self.satellites.items():
            self._calculate_and_cache_passes(station, name, sat_obj, targets)

    def _remove_pass_from_cache(self, sat_name: str):
        """Remove a primeira passagem da lista de um satélite."""
        with self.predictions_lock:
            if self.pass_predictions.get(sat_name):
                self.pass_predictions[sat_name].pop(0)