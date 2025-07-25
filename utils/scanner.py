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
from .sdr_manager import sdr_manager # Importa a instância do gerenciador

def check_hardware_status():
    """Verifica o status do hardware usando o lock do gerenciador para evitar conflitos."""
    sdr = sdr_manager.acquire_device()
    if sdr:
        driver = sdr.getDriverKey()
        sdr_manager.release_device()
        return True, f"HackRF One Conectado ({driver})"
    else:
        # Se acquire_device falhou, ele já liberou o lock.
        # Não precisamos chamar release_device() aqui.
        return False, "HackRF One Não Encontrado"

def load_config():
    """Carrega as configurações do arquivo JSON."""
    with open("config.json", "r") as f:
        return json.load(f)

def monitor_amateur_radio(duration_seconds: int, scanner_event):
    """Escaneia frequências de rádio amador usando o SDRManager."""
    config = load_config().get('amateur_radio_monitoring', {})
    if not config.get('enabled', False):
        time.sleep(duration_seconds)
        return

    print(f"📻 Entrando em modo de monitoramento por ~{duration_seconds / 60:.0f} min.")
    sdr = sdr_manager.acquire_device()
    if not sdr:
        print("❌ Não foi possível adquirir o SDR para monitoramento.")
        time.sleep(duration_seconds)
        return

    rxStream = None
    start_time = time.time()
    try:
        # Configurações para o scan
        sdr.setSampleRate(SOAPY_SDR_RX, 0, 1e6)
        sdr.setGain(SOAPY_SDR_RX, 0, 35)
        rxStream = sdr.setupStream(SOAPY_SDR_RX, SOAPY_SDR_CF32)
        sdr.activateStream(rxStream)
        sdr_manager.active_stream = rxStream # Informa ao manager sobre o stream

        samples = np.zeros(1024, np.complex64)
        frequencies = [f * 1e6 for f in config['frequencies_mhz']]
        squelch_threshold = 10**(config['squelch_db'] / 10)

        while time.time() - start_time < duration_seconds:
            if not scanner_event.is_set():
                scanner_event.wait()

            for freq in frequencies:
                if time.time() - start_time >= duration_seconds: break
                sdr.setFrequency(SOAPY_SDR_RX, 0, freq)
                sdr.readStream(rxStream, [samples], len(samples), timeoutUs=int(0.01 * 1e6))
                power = np.mean(np.abs(samples)**2)
                
                if power > squelch_threshold:
                    print(f"    -> Sinal detectado em {freq/1e6:.3f} MHz! Pausando por {config['dwell_seconds']}s...")
                    time.sleep(config['dwell_seconds'])
    except Exception as e:
        print(f"❌ Erro durante o monitoramento: {e}")
    finally:
        if sdr and rxStream:
            sdr.deactivateStream(rxStream)
            sdr.closeStream(rxStream)
            sdr_manager.active_stream = None
        sdr_manager.release_device()
        print("📻 Saindo do modo de monitoramento.")

def real_capture(target_info):
    """Realiza uma captura de sinal usando o SDRManager."""
    config = load_config()
    sdr_settings = config['sdr_settings']
    
    sdr = sdr_manager.acquire_device()
    if not sdr:
        print("❌ Não foi possível adquirir o SDR para captura.")
        return

    rxStream = None
    try:
        # Configura o SDR para a captura de alta qualidade
        sdr.setSampleRate(SOAPY_SDR_RX, 0, sdr_settings['sample_rate'])
        sdr.setFrequency(SOAPY_SDR_RX, 0, target_info['frequency'])
        sdr.setGain(SOAPY_SDR_RX, 0, sdr_settings['gain'])
        
        rxStream = sdr.setupStream(SOAPY_SDR_RX, SOAPY_SDR_CF32)
        sdr.activateStream(rxStream)
        sdr_manager.active_stream = rxStream
        
        samples_to_capture = int(sdr_settings['sample_rate'] * target_info['capture_duration_seconds'])
        samples = np.zeros(samples_to_capture, np.complex64)
        
        print(f"    -> Gravando por {target_info['capture_duration_seconds']} segundos...")
        sdr.readStream(rxStream, [samples], len(samples))

    except Exception as e:
        print(f"❌ Erro durante a captura com SDR: {e}")
        samples = None
    finally:
        if sdr and rxStream:
            sdr.deactivateStream(rxStream)
            sdr.closeStream(rxStream)
            sdr_manager.active_stream = None
        sdr_manager.release_device()

    if samples is None or np.sum(np.abs(samples)) == 0:
        print("❌ Captura falhou, nenhum dado foi lido do SDR.")
        return

    # Processamento e salvamento do arquivo...
    # (O restante desta função permanece o mesmo)
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