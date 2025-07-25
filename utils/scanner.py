# utils/scanner.py
import SoapySDR
from SoapySDR import *
import numpy as np
import datetime
from scipy.io import wavfile
import os
import json
import time
from utils import db, decoder

# Força o PATH para encontrar DLLs do Soapy, se necessário
extra = r"C:\ProgramData\radioconda\Library\bin;C:\ProgramData\radioconda\Library\lib"
if extra not in os.environ.get("PATH", ""):
    os.environ["PATH"] = extra + ";" + os.environ.get("PATH", "")

def get_hackrf_device():
    """Encontra e retorna o primeiro dispositivo HackRF disponível."""
    devices = SoapySDR.Device.enumerate()
    for dev in devices:
        if "driver" in dev and dev["driver"] == "hackrf":
            print(f"✔️ Dispositivo HackRF encontrado: {dev}")
            return dev
    print("❌ Nenhum dispositivo HackRF encontrado na lista de dispositivos SDR.")
    return None

def check_hardware_status():
    """Verifica o status do hardware, procurando especificamente pelo HackRF."""
    try:
        hackrf_device = get_hackrf_device()
        if not hackrf_device:
            return False, "HackRF One Não Encontrado"
        sdr = SoapySDR.Device(hackrf_device)
        driver = sdr.getDriverKey()
        return True, f"HackRF One Conectado ({driver})"
    except Exception as e:
        return False, f"Erro ao acessar HackRF: {e}"

def load_config():
    """Carrega as configurações do arquivo JSON."""
    with open("config.json", "r") as f:
        return json.load(f)

# --- NOVA FUNÇÃO PARA MONITORAMENTO ---
def monitor_amateur_radio(duration_seconds: int, scanner_event):
    """Escaneia frequências de rádio amador por um período definido."""
    config = load_config().get('amateur_radio_monitoring', {})
    if not config.get('enabled', False):
        print("-> Monitoramento de rádio amador desativado na configuração.")
        time.sleep(duration_seconds)
        return

    print(f"📻 Entrando em modo de monitoramento de rádio amador por ~{duration_seconds / 60:.0f} minutos.")
    
    sdr = None
    rxStream = None
    start_time = time.time()
    
    try:
        hackrf_device = get_hackrf_device()
        if not hackrf_device:
            print("❌ HackRF não encontrado para iniciar o monitoramento.")
            time.sleep(duration_seconds)
            return

        sdr = SoapySDR.Device(hackrf_device)
        sdr.setSampleRate(SOAPY_SDR_RX, 0, 1e6) # Taxa de amostragem menor para scan
        sdr.setGain(SOAPY_SDR_RX, 0, 35)

        rxStream = sdr.setupStream(SOAPY_SDR_RX, SOAPY_SDR_CF32)
        sdr.activateStream(rxStream)

        samples = np.zeros(1024, np.complex64)
        frequencies = [f * 1e6 for f in config['frequencies_mhz']] # Converte para Hz
        squelch_threshold = 10**(config['squelch_db'] / 10)

        while time.time() - start_time < duration_seconds:
            if not scanner_event.is_set():
                print("⏸️ Monitoramento pausado pelo usuário.")
                scanner_event.wait()
                print("▶️ Monitoramento reativado.")

            for freq in frequencies:
                sdr.setFrequency(SOAPY_SDR_RX, 0, freq)
                sdr.readStream(rxStream, [samples], len(samples), timeoutUs=int(0.01 * 1e6))
                
                power = np.mean(np.abs(samples)**2)
                
                if power > squelch_threshold:
                    print(f"    -> Sinal detectado em {freq/1e6:.3f} MHz! Ouvindo por {config['dwell_seconds']}s...")
                    time.sleep(config['dwell_seconds'])
                
                # Verifica o tempo restante após cada frequência
                if time.time() - start_time >= duration_seconds:
                    break
        
    except Exception as e:
        print(f"❌ Erro durante o monitoramento de rádio amador: {e}")
    finally:
        if sdr and rxStream:
            sdr.deactivateStream(rxStream)
            sdr.closeStream(rxStream)
        print("📻 Saindo do modo de monitoramento.")


def real_capture(target_info):
    # (Esta função permanece a mesma da versão anterior)
    config = load_config()
    sdr_settings = config['sdr_settings']
    
    sdr = None
    rxStream = None
    try:
        hackrf_device = get_hackrf_device()
        if not hackrf_device:
            print("❌ Nenhum HackRF disponível para captura.")
            return

        sdr = SoapySDR.Device(hackrf_device)
        sdr.setSampleRate(SOAPY_SDR_RX, 0, sdr_settings['sample_rate'])
        sdr.setFrequency(SOAPY_SDR_RX, 0, target_info['frequency'])
        sdr.setGain(SOAPY_SDR_RX, 0, sdr_settings['gain'])
        
        rxStream = sdr.setupStream(SOAPY_SDR_RX, SOAPY_SDR_CF32)
        sdr.activateStream(rxStream)

        samples_to_capture = int(sdr_settings['sample_rate'] * target_info['capture_duration_seconds'])
        samples = np.zeros(samples_to_capture, np.complex64)
        
        print(f"    -> Gravando por {target_info['capture_duration_seconds']} segundos...")
        sdr.readStream(rxStream, [samples], len(samples))

    except Exception as e:
        print(f"❌ Erro durante a captura com SDR: {e}")
        return
    finally:
        if sdr and rxStream:
            sdr.deactivateStream(rxStream)
            sdr.closeStream(rxStream)

    if 'samples' not in locals() or np.sum(np.abs(samples)) == 0:
        print("❌ Captura falhou, nenhum dado foi lido do SDR.")
        return

    samples_real = (np.real(samples) * 32767).astype(np.int16)
    samples_imag = (np.imag(samples) * 32767).astype(np.int16)
    
    timestamp = datetime.datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
    filename = f"{target_info['name'].replace(' ', '_')}_{timestamp}.wav"
    filepath = os.path.join("captures", filename)
    
    os.makedirs("captures", exist_ok=True)
    
    stereo_samples = np.vstack((samples_real, samples_imag)).T
    wavfile.write(filepath, int(sdr_settings['sample_rate']), stereo_samples)

    db.insert_signal(
        target=target_info['name'],
        frequency=target_info['frequency'],
        timestamp=timestamp,
        filepath=filepath,
    )
    print(f"💾 Sinal salvo em: {filepath}")

    if "NOAA" in target_info['name']:
        decoder.decode_apt(filepath)