# utils/scanner.py
import SoapySDR
from SoapySDR import *
import numpy as np
import datetime
from scipy.io.wavfile import write as write_wav
import os
import json

# Importação corrigida para o formato absoluto
from utils import db

def load_config():
    """Carrega as configurações do arquivo JSON."""
    with open("config.json", "r") as f:
        return json.load(f)

def real_capture(target_info):
    """Configura o SDR, captura o sinal e salva em WAV."""
    config = load_config()
    sdr_settings = config['sdr_settings']
    
    try:
        sdr = SoapySDR.Device({"driver": "hackrf"})
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