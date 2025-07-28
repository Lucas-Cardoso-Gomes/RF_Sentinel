# utils/scanner.py
import SoapySDR
from SoapySDR import *
import numpy as np
import datetime
import wave
import os
import json
import time
from utils import db, decoder
from utils.logger import logger
from utils.sdr_manager import sdr_manager

def apply_gain_settings(sdr, gains):
    """Aplica as configurações de ganho LNA, VGA e AMP ao dispositivo SDR."""
    if sdr and gains:
        try:
            if "lna" in gains: sdr.setGain(SOAPY_SDR_RX, 0, "LNA", gains["lna"])
            if "vga" in gains: sdr.setGain(SOAPY_SDR_RX, 0, "VGA", gains["vga"])
            if "amp" in gains: sdr.setGain(SOAPY_SDR_RX, 0, "AMP", gains["amp"])
            logger.log(f"Ganhos configurados: LNA={gains.get('lna', 'N/A')}, VGA={gains.get('vga', 'N/A')}", "DEBUG")
        except Exception as e:
            logger.log(f"Falha ao aplicar ganhos: {e}", "ERROR")

def perform_monitoring(sdr, duration_seconds: int, scanner_event):
    """Executa o scan de rádio amador em um dispositivo SDR já adquirido."""
    config = json.load(open("config.json", "r")).get('amateur_radio_monitoring', {})
    if not config.get('enabled', False):
        time.sleep(duration_seconds)
        return

    rxStream = None
    start_time = time.time()
    try:
        sdr.setSampleRate(SOAPY_SDR_RX, 0, 1e6)
        apply_gain_settings(sdr, config.get("gains"))
        rxStream = sdr.setupStream(SOAPY_SDR_RX, SOAPY_SDR_CF32)
        sdr.activateStream(rxStream)
        
        samples = np.zeros(1024, np.complex64)
        frequencies = [f * 1e6 for f in config['frequencies_mhz']]
        squelch_threshold = 10**(config['squelch_db'] / 10)

        # --- LÓGICA DE SCAN RESTAURADA ---
        while time.time() - start_time < duration_seconds:
            if not scanner_event.is_set(): scanner_event.wait()
            
            for freq in frequencies:
                if time.time() - start_time >= duration_seconds: break
                
                sdr.setFrequency(SOAPY_SDR_RX, 0, freq)
                sdr.readStream(rxStream, [samples], len(samples), timeoutUs=int(0.01 * 1e6))
                power = np.mean(np.abs(samples)**2)
                
                if power > squelch_threshold:
                    logger.log(f"Sinal detectado em {freq/1e6:.3f} MHz! Pausando por {config['dwell_seconds']}s...", "INFO")
                    time.sleep(config['dwell_seconds'])
    finally:
        if sdr and rxStream:
            sdr.deactivateStream(rxStream)
            sdr.closeStream(rxStream)

def perform_capture(sdr, target_info):
    """Executa a captura de sinal em streaming."""
    config = json.load(open("config.json", "r"))
    sdr_settings = config['sdr_settings']
    rxStream = None
    filepath = ""
    timestamp = datetime.datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
    
    try:
        sample_rate = sdr_settings['sample_rate']
        sdr.setSampleRate(SOAPY_SDR_RX, 0, sample_rate)
        sdr.setFrequency(SOAPY_SDR_RX, 0, target_info['frequency'])
        apply_gain_settings(sdr, target_info.get("gains"))
        
        rxStream = sdr.setupStream(SOAPY_SDR_RX, SOAPY_SDR_CF32)
        sdr.activateStream(rxStream)
        
        chunk_size = 1024 * 32
        samples_buffer = np.zeros(chunk_size, np.complex64)
        total_samples_to_capture = int(sample_rate * target_info['capture_duration_seconds'])
        samples_captured = 0

        filename = f"{target_info['name'].replace(' ', '_')}_{timestamp}.wav"
        filepath = os.path.join("captures", filename)
        os.makedirs("captures", exist_ok=True)

        logger.log(f"Gravando por {target_info['capture_duration_seconds']}s para {filepath}...", "INFO")
        with wave.open(filepath, 'wb') as wf:
            wf.setnchannels(2)
            wf.setsampwidth(2)
            wf.setframerate(int(sample_rate))
            
            while samples_captured < total_samples_to_capture:
                sr = sdr.readStream(rxStream, [samples_buffer], len(samples_buffer))
                if sr.ret <= 0: continue
                chunk = samples_buffer[:sr.ret]
                samples_real = (np.real(chunk) * 32767).astype(np.int16)
                samples_imag = (np.imag(chunk) * 32767).astype(np.int16)
                stereo_chunk = np.vstack((samples_real, samples_imag)).T
                wf.writeframes(stereo_chunk.tobytes())
                samples_captured += sr.ret
    finally:
        # --- BUG CRÍTICO CORRIGIDO ---
        # Garante que o stream seja sempre fechado, independentemente de erros.
        if sdr and rxStream:
            sdr.deactivateStream(rxStream)
            sdr.closeStream(rxStream)

    if os.path.exists(filepath):
        logger.log(f"Sinal salvo em: {filepath}", "SUCCESS")
        db.insert_signal(target=target_info['name'], frequency=target_info['frequency'], timestamp=timestamp, filepath=filepath)
        if "NOAA" in target_info['name']:
            decoder.decode_apt(filepath)