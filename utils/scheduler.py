# utils/scheduler.py
import time
import datetime
import json
from skyfield.api import load, EarthSatellite, Topos

import tle
# Importamos a nova função de verificação
from utils.scanner import real_capture, check_hardware_status

ts = load.timescale()

def load_config():
    """Carrega as configurações do arquivo JSON."""
    with open("config.json", "r") as f:
        return json.load(f)

def get_next_pass(station, satellite):
    """Calcula a próxima passagem visível de um satélite."""
    now = ts.now()
    t0 = now
    # Procura por passagens nas próximas 24 horas
    t1 = ts.utc(now.utc_datetime() + datetime.timedelta(days=1))
    
    times, events = satellite.find_events(station, t0, t1, altitude_degrees=10.0)
    
    # Itera pelos eventos para encontrar a primeira passagem completa (nascer, culminar, se pôr)
    for i in range(len(events) - 2):
        if events[i] == 0 and events[i+1] == 1 and events[i+2] == 2:
            pass_start = times[i]
            # Garante que a passagem encontrada está no futuro
            if pass_start.utc_datetime() > datetime.datetime.utcnow().replace(tzinfo=datetime.timezone.utc):
                return pass_start, times[i+2]
    return None, None

def scheduler_loop(scanner_event, hackrf_status_dict):
    """Loop principal que agenda as capturas."""
    
    print("🛰️  Agendador iniciado. Verificando hardware...")
    connected, status_text = check_hardware_status()
    hackrf_status_dict["connected"] = connected
    hackrf_status_dict["status_text"] = status_text
    print(f"📡 Status do HackRF: {status_text}")
    
    config = load_config()
    station_config = config['station']
    station_geo = Topos(
        latitude_degrees=float(station_config['latitude'].split()[0]),
        longitude_degrees=float(station_config['longitude'].split()[0]),
        elevation_m=station_config['elevation_m']
    )
    targets = config['targets']
    satellites = {}

    print("Baixando dados TLE...")
    for target in targets:
        tle_data = tle.fetch_tle_from_url(target['tle_url'])
        if tle_data:
            print(f"  - TLE para {target['name']} OK")
            lines = tle_data.strip().splitlines()
            # Lida com formatos de TLE de 2 ou 3 linhas
            if len(lines) >= 3:
                satellites[target['name']] = EarthSatellite(lines[1], lines[2], lines[0], ts)
            else:
                satellites[target['name']] = EarthSatellite(lines[0], lines[1], target['name'], ts)
        else:
            print(f"  - Falha ao obter TLE para {target['name']}")

    # Se nenhum TLE pôde ser carregado, faz uma pausa longa
    if not satellites:
        print("❌ Nenhum dado TLE pôde ser carregado. Verifique a conexão e as URLs.")
        print("   Tentando novamente em 15 minutos...")
        time.sleep(900)

    while True:
        # Atualiza o status do hardware a cada ciclo
        connected, status_text = check_hardware_status()
        hackrf_status_dict["connected"] = connected
        hackrf_status_dict["status_text"] = status_text

        if not connected:
            print(f"❌ HackRF desconectado: {status_text}. Aguardando reconexão...")
            time.sleep(10)
            continue

        if not scanner_event.is_set():
            print("⏸️ Scanner pausado. Aguardando reativação...")
            time.sleep(10)
            continue

        next_pass_time = None
        target_for_next_pass = None

        print("\nBuscando a passagem de satélite mais próxima...")
        for name, sat in satellites.items():
            start, end = get_next_pass(station_geo, sat)
            
            if start is not None:
                print(f"  - Próxima passagem de {name}: {start.utc_strftime('%Y-%m-%d %H:%M:%S UTC')}")
                if next_pass_time is None or start < next_pass_time:
                    next_pass_time = start
                    target_for_next_pass = next((t for t in targets if t['name'] == name), None)

        if next_pass_time is not None and target_for_next_pass is not None:
            wait_seconds = (next_pass_time.utc_datetime() - datetime.datetime.utcnow().replace(tzinfo=datetime.timezone.utc)).total_seconds()
            
            if wait_seconds > 0:
                print(f"\n✅ Próxima captura agendada para {target_for_next_pass['name']}.")
                print(f"   Aguardando {int(wait_seconds // 60)} minutos e {int(wait_seconds % 60)} segundos...")
                
                # Loop de espera que pode ser interrompido
                sleep_end_time = time.time() + wait_seconds
                while time.time() < sleep_end_time:
                    if not scanner_event.is_set():
                        print("\n⏸️  Scanner pausado pelo usuário. Agendamento em espera.")
                        scanner_event.wait() # Pausa a thread até o evento ser reativado
                        print("▶️  Scanner reativado. Retomando contagem...")
                        # Recalcula o tempo de espera restante
                        sleep_end_time = time.time() + (next_pass_time.utc_datetime() - datetime.datetime.utcnow().replace(tzinfo=datetime.timezone.utc)).total_seconds()
                    time.sleep(1)

            # Garante que a captura só aconteça se o tempo de espera tiver passado
            if wait_seconds <= 1: # Pequena margem para evitar pular capturas
                print(f"\n📡 Capturando passagem de {target_for_next_pass['name']} agora!")
                real_capture(target_for_next_pass)
                print("✅ Captura finalizada. Procurando a próxima passagem.")
                time.sleep(10) # Pausa para evitar loops rápidos
            
        else:
            print("Nenhuma passagem encontrada nas próximas 24 horas. Verificando novamente em 1 hora.")
            time.sleep(3600)