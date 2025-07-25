# utils/scanner.py
import SoapySDR
from SoapySDR import *
import numpy as np
import datetime
from scipy.io import wavfile
import os
import json
from utils import db, decoder

# Força o PATH para encontrar DLLs do Soapy, se necessário
extra = r"C:\ProgramData\radioconda\Library\bin;C:\ProgramData\radioconda\Library\lib"
if extra not in os.environ.get("PATH", ""):
    os.environ["PATH"] = extra + ";" + os.environ.get("PATH", "")

def get_hackrf_device():
    """Encontra e retorna o primeiro dispositivo HackRF disponível."""
    devices = SoapySDR.Device.enumerate()
    for dev in devices:
        # --- CORREÇÃO APLICADA AQUI ---
        # Acessa a chave 'driver' usando a sintaxe de dicionário
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
        
        # Usa os argumentos do dispositivo encontrado para abri-lo
        sdr = SoapySDR.Device(hackrf_device)
        driver = sdr.getDriverKey()
        return True, f"HackRF One Conectado ({driver})"
    except Exception as e:
        return False, f"Erro ao acessar HackRF: {e}"

def load_config():
    """Carrega as configurações do arquivo JSON."""
    with open("config.json", "r") as f:
        return json.load(f)

def real_capture(target_info):
    """Configura o SDR, captura o sinal e salva em WAV."""
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
        return # Retorna para evitar processar um sinal vazio
    finally:
        if sdr and rxStream:
            sdr.deactivateStream(rxStream)
            sdr.closeStream(rxStream)

    if 'samples' not in locals() or np.sum(np.abs(samples)) == 0:
        print("❌ Captura falhou, nenhum dado foi lido do SDR.")
        return

    # Processamento e salvamento do arquivo
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