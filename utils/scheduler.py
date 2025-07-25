# utils/scheduler.py
import time
import datetime
import json
from skyfield.api import load, EarthSatellite, Topos
import os
import tle
from utils.scanner import real_capture, check_hardware_status, monitor_amateur_radio

ts = load.timescale()
PASS_LOG_FILE = "pass_log.json"

def load_config():
    """Carrega as configurações do arquivo JSON."""
    with open("config.json", "r") as f:
        return json.load(f)

def get_next_pass(station, satellite):
    """Calcula a próxima passagem visível de um satélite."""
    now = ts.now()
    t0 = now
    # Procura por passagens nas próximas 48 horas para ter uma boa margem
    t1 = ts.utc(now.utc_datetime() + datetime.timedelta(days=2))
    
    times, events = satellite.find_events(station, t0, t1, altitude_degrees=10.0)
    
    # Itera pelos eventos para encontrar a primeira passagem completa (nascer, culminar, se pôr)
    for i in range(len(events) - 2):
        if events[i] == 0 and events[i + 1] == 1 and events[i + 2] == 2:
            pass_start = times[i]
            # Garante que a passagem encontrada está no futuro
            if pass_start.utc_datetime() > datetime.datetime.utcnow().replace(tzinfo=datetime.timezone.utc):
                return pass_start, times[i+2]
    return None, None

def save_pass_log(passes):
    """Salva a lista de próximas passagens em um arquivo JSON."""
    try:
        with open(PASS_LOG_FILE, 'w') as f:
            # Converte objetos skyfield para strings antes de salvar
            serializable_passes = []
            for p in passes:
                serializable_passes.append({
                    'name': p['name'],
                    'start_utc': p['start'].utc_iso(),
                    'end_utc': p['end'].utc_iso(),
                    'target_info': p['target_info']
                })
            json.dump(serializable_passes, f, indent=4)
    except Exception as e:
        print(f"❌ Erro ao salvar o log de passagens: {e}")

def load_pass_log():
    """Carrega a lista de próximas passagens do arquivo JSON."""
    if not os.path.exists(PASS_LOG_FILE):
        return []
    try:
        with open(PASS_LOG_FILE, 'r') as f:
            log_data = json.load(f)
            passes = []
            now_utc = datetime.datetime.now(datetime.timezone.utc)
            for entry in log_data:
                start_time = ts.from_datetime(datetime.datetime.fromisoformat(entry['start_utc']))
                # Só carrega passagens que ainda não aconteceram
                if start_time.utc_datetime() > now_utc:
                    passes.append({
                        'name': entry['name'],
                        'start': start_time,
                        'end': ts.from_datetime(datetime.datetime.fromisoformat(entry['end_utc'])),
                        'target_info': entry['target_info']
                    })
            return passes
    except Exception as e:
        print(f"❌ Erro ao carregar o log de passagens: {e}")
        return []

def scheduler_loop(scanner_event, shared_status, waterfall_event):
    """Loop principal que agenda as capturas."""
    
    def log(message, level='INFO'):
        print(message)
        log_entry = {
            "timestamp": datetime.datetime.now().strftime('%H:%M:%S'),
            "level": level,
            "message": message
        }
        shared_status['scheduler_log'].append(log_entry)
        if len(shared_status['scheduler_log']) > 20:
            shared_status['scheduler_log'].pop(0)

    log("🛰️  Agendador iniciado.")
    config = load_config()
    station_config = config['station']
    station_geo = Topos(
        latitude_degrees=float(station_config['latitude'].split()[0]),
        longitude_degrees=float(station_config['longitude'].split()[0]),
        elevation_m=station_config['elevation_m']
    )
    targets = config['targets']
    satellites = {}
    last_tle_update = 0

    while True:
        # --- ATUALIZAÇÃO PERIÓDICA DE TLE ---
        if not satellites or (time.time() - last_tle_update) > 6 * 3600: # Atualiza a cada 6 horas
            log("Atualizando dados TLE dos satélites...")
            
            tle_groups = {}
            download_success = True
            for target in targets:
                url = target['tle_url']
                if url not in tle_groups:
                    tle_groups[url] = tle.fetch_tle_from_url(url)
                    if tle_groups[url] is None:
                        download_success = False

            if download_success:
                satellites.clear() # Limpa a lista antiga antes de popular
                for target in targets:
                    group_text = tle_groups.get(target['tle_url'])
                    if group_text:
                        tle_lines = tle.extract_tle_from_group(group_text, target['name'])
                        if tle_lines and len(tle_lines) == 3:
                            satellites[target['name']] = EarthSatellite(tle_lines[1], tle_lines[2], tle_lines[0], ts)
                        else:
                            log(f"  - Falha ao EXTRAIR TLE para {target['name']}")
                log(f"Dados TLE atualizados para {len(satellites)} satélite(s).")
                last_tle_update = time.time()
            else:
                log("⚠️ Falha no download dos TLEs. Usando dados antigos se disponíveis.")

        # --- LÓGICA DE AGENDAMENTO ---
        connected, status_text = check_hardware_status()
        shared_status["hackrf_status"]["connected"] = connected
        shared_status["hackrf_status"]["status_text"] = status_text

        if not connected:
            log(f"❌ HackRF desconectado: {status_text}. Aguardando...")
            time.sleep(10)
            continue

        if not scanner_event.is_set():
            log("⏸️ Scanner pausado.")
            time.sleep(10)
            continue
            
        # Calcula todas as passagens futuras com os TLEs disponíveis
        all_future_passes = []
        if satellites:
            for name, sat in satellites.items():
                start, end = get_next_pass(station_geo, sat)
                if start:
                    all_future_passes.append({
                        "name": name, 
                        "start": start, 
                        "end": end,
                        "target_info": next((t for t in targets if t['name'] == name), None)
                    })
            all_future_passes.sort(key=lambda p: p['start'].utc_datetime())
            save_pass_log(all_future_passes[:5]) # Salva as próximas 5
        else:
            all_future_passes = load_pass_log()

        if all_future_passes:
            next_pass = all_future_passes[0]
            shared_status['next_pass'] = {'name': next_pass['name'], 'start_utc': next_pass['start'].utc_iso()}
            wait_seconds = (next_pass['start'].utc_datetime() - datetime.datetime.utcnow().replace(tzinfo=datetime.timezone.utc)).total_seconds()

            if wait_seconds <= 60: # Se a captura está iminente (menos de 60s)
                if waterfall_event.is_set():
                    log("🔴 Pausando waterfall para captura prioritária.")
                    waterfall_event.clear() # SINAL VERMELHO
                    time.sleep(5) # Dá tempo para o websocket fechar
                
                if wait_seconds > 0:
                    log(f"Aguardando contagem final para {next_pass['name']}...")
                    time.sleep(wait_seconds)
                
                log(f"📡 Capturando passagem de {next_pass['name']} agora!")
                real_capture(next_pass['target_info'])
                log("✅ Captura finalizada.")
                
                log("🟢 Reativando waterfall.")
                waterfall_event.set() # SINAL VERDE
                shared_status['next_pass'] = None
                time.sleep(10)
            
            elif wait_seconds > 300: # Se a espera é longa (mais de 5 min)
                monitor_duration = wait_seconds - 120 # Deixa 2 min de folga
                log(f"Próxima passagem em {wait_seconds / 60:.0f} min. Entrando em modo de monitoramento.")
                monitor_amateur_radio(monitor_duration, scanner_event)
            
            else: # Se a espera é curta (entre 1 e 5 min)
                log(f"✅ Próxima captura: {next_pass['name']} em {int(wait_seconds // 60)}m {int(wait_seconds % 60)}s.")
                time.sleep(5) # Pausa curta antes de reavaliar
        else:
            shared_status['next_pass'] = None
            log("Nenhuma passagem futura encontrada. Verificando novamente em 15 minutos.")
            time.sleep(900)