# utils/scheduler.py
import time
import datetime
import json
import os
import threading
import tle
from skyfield.api import load, EarthSatellite, Topos
from utils.scanner import perform_capture, perform_monitoring
from utils.sdr_manager import sdr_manager
from utils.logger import logger

class Scheduler(threading.Thread):
    def __init__(self, scanner_event, shared_status, waterfall_event):
        super().__init__()
        self.scanner_event = scanner_event
        self.shared_status = shared_status
        self.waterfall_event = waterfall_event
        self.ts = load.timescale()
        self._stop_event = threading.Event()
        self.daemon = True

    def stop(self):
        self._stop_event.set()

    def get_next_pass(self, station, satellite):
        now = self.ts.now()
        t1 = self.ts.utc(now.utc_datetime() + datetime.timedelta(days=2))
        times, events = satellite.find_events(station, now, t1, altitude_degrees=10.0)
        for i in range(len(events) - 2):
            if events[i] == 0 and events[i + 1] == 1 and events[i + 2] == 2:
                if times[i].utc_datetime() > datetime.datetime.utcnow().replace(tzinfo=datetime.timezone.utc):
                    return times[i], times[i+2]
        return None, None

    def run(self):
        logger.log("Agendador iniciado.", "INFO")
        config = json.load(open("config.json", "r"))
        station_geo = Topos(latitude_degrees=float(config['station']['latitude'].split()[0]), longitude_degrees=float(config['station']['longitude'].split()[0]), elevation_m=config['station']['elevation_m'])
        targets = config['targets']
        satellites = {}
        last_tle_update = 0

        while not self._stop_event.is_set():
            try:
                if not satellites or (time.time() - last_tle_update) > 6 * 3600:
                    logger.log("Atualizando dados TLE...", "INFO")
                    tle_groups = {}
                    download_success = True
                    for target in targets:
                        url = target['tle_url']
                        if url not in tle_groups:
                            tle_groups[url] = tle.fetch_tle_from_url(url)
                            if tle_groups[url] is None:
                                download_success = False
                    
                    if download_success:
                        satellites.clear()
                        for target in targets:
                            group_text = tle_groups.get(target['tle_url'])
                            if group_text:
                                tle_lines = tle.extract_tle_from_group(group_text, target['name'])
                                if tle_lines:
                                    satellites[target['name']] = EarthSatellite(tle_lines[1], tle_lines[2], tle_lines[0], self.ts)
                        logger.log(f"Dados TLE atualizados para {len(satellites)} satélite(s).", "SUCCESS")
                        last_tle_update = time.time()
                    else:
                        logger.log("Falha no download dos TLEs. Usando dados antigos se disponíveis.", "WARN")

                sdr_dev = sdr_manager.find_hackrf()
                self.shared_status["hackrf_status"]["connected"] = bool(sdr_dev)
                self.shared_status["hackrf_status"]["status_text"] = "HackRF Conectado" if sdr_dev else "HackRF Desconectado"

                if not sdr_dev:
                    logger.log("HackRF desconectado. Aguardando...", "ERROR")
                    time.sleep(10)
                    continue

                if not self.scanner_event.is_set():
                    logger.log("Scanner pausado.", "WARN")
                    time.sleep(10)
                    continue

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

                    if wait_seconds <= 60:
                        self.waterfall_event.clear()
                        logger.log(f"Captura iminente de {next_pass['name']}. Pausando waterfall.", "WARN")
                        if wait_seconds > 5: time.sleep(wait_seconds - 5)
                        
                        sdr = sdr_manager.acquire()
                        if sdr:
                            try:
                                logger.log(f"Capturando {next_pass['name']}...")
                                perform_capture(sdr, next_pass['target_info'])
                            finally:
                                sdr_manager.release()
                                logger.log("Captura finalizada.", "SUCCESS")
                        
                        self.waterfall_event.set()
                        self.shared_status['next_pass'] = None
                        time.sleep(10)
                    
                    elif wait_seconds > 300:
                        monitor_duration = wait_seconds - 60
                        logger.log(f"Tempo ocioso. Monitorando rádio amador por ~{monitor_duration/60:.0f} min.", "INFO")
                        sdr = sdr_manager.acquire()
                        if sdr:
                            try:
                                perform_monitoring(sdr, monitor_duration, self.scanner_event)
                            finally:
                                sdr_manager.release()
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