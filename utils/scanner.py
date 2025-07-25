# utils/scanner.py
import SoapySDR
from SoapySDR import *
import numpy as np
import datetime
from scipy.io.wavfile import write as write_wav
import os
import json
from utils import db
import os, sys

# Força o PATH para encontrar DLLs do Soapy
extra = r"C:\ProgramData\radioconda\Library\bin;C:\ProgramData\radioconda\Library\lib"
os.environ["PATH"] = extra + ";" + os.environ.get("PATH", "")

# --- Função dedicada a verificar o hardware SDR ---
def check_hardware_status():
    print("🧪 DEBUG: módulos SoapySDR encontrados:", SoapySDR.listModules())
    print("🧪 DEBUG: root path:", SoapySDR.getRootPath())
    try:
        available = SoapySDR.Device.enumerate()
        print("🧪 DEBUG: Dispositivos SoapySDR disponíveis:")
        for i, dev in enumerate(available):
            print(f"  [{i}] {dev}")

        if not available:
            return False, "Nenhum dispositivo SDR detectado"

        sdr = SoapySDR.Device(available[0])
        driver = sdr.getDriverKey()
        print("🧪 DEBUG: SDR aberto com driver:", driver)
        return True, f"Dispositivo SDR detectado: {driver}"
    except Exception as e:
        return False, f"HackRF não encontrado: {e}"


def load_config():
    """Carrega as configurações do arquivo JSON."""
    with open("config.json", "r") as f:
        return json.load(f)


def real_capture(target_info):
    """Configura o SDR, captura o sinal e salva em WAV."""
    config = load_config()
    sdr_settings = config['sdr_settings']
    
    try:
        available = SoapySDR.Device.enumerate()
        if not available:
            print("❌ Nenhum SDR disponível para captura.")
            return

        sdr = SoapySDR.Device(available[0])
        sdr.setSampleRate(SOAPY_SDR_RX, 0, sdr_settings['sample_rate'])
        sdr.setFrequency(SOAPY_SDR_RX, 0, target_info['frequency'])
        sdr.setGain(SOAPY_SDR_RX, 0, sdr_settings['gain'])
    except Exception as e:
        print(f"❌ Erro ao inicializar o SDR: {e}")
        print("   Verifique se o HackRF One está conectado e os drivers estão instalados.")
        return

    rxStream = sdr.setupStream(SOAPY_SDR_RX, SOAPY_SDR_CF32)
    sdr.activateStream(rxStream)

    samples_to_capture = int(sdr_settings['sample_rate'] * target_info['capture_duration_seconds'])
    samples = np.zeros(samples_to_capture, np.complex64)
    
    print(f"    -> Gravando por {target_info['capture_duration_seconds']} segundos...")
    sdr.readStream(rxStream, [samples], len(samples))

    sdr.deactivateStream(rxStream)
    sdr.closeStream(rxStream)

    samples_real = (np.real(samples) * 32767).astype(np.int16)
    samples_imag = (np.imag(samples) * 32767).astype(np.int16)
    
    timestamp = datetime.datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
    filename = f"{target_info['name'].replace(' ', '_')}_{timestamp}.wav"
    filepath = os.path.join("captures", filename)
    
    os.makedirs("captures", exist_ok=True)
    
    stereo_samples = np.vstack((samples_real, samples_imag)).T
    write_wav(filepath, int(sdr_settings['sample_rate']), stereo_samples)

    db.insert_signal(
        target=target_info['name'],
        frequency=target_info['frequency'],
        timestamp=timestamp,
        filepath=filepath,
    )
    print(f"💾 Sinal salvo em: {filepath}")
