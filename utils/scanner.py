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

def perform_capture(sdr, target_info):
    """
    Executa a captura de sinal com uma configuração simplificada e robusta para máxima compatibilidade.
    """
    rxStream = None
    filepath = ""
    timestamp = datetime.datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
    
    try:
        # --- Configuração Simplificada ---
        sample_rate = target_info.get('sample_rate', 2.4e6)
        frequency = target_info.get('frequency', 100e6)
        
        sdr.setSampleRate(SOAPY_SDR_RX, 0, sample_rate)
        sdr.setFrequency(SOAPY_SDR_RX, 0, frequency)
        
        # Ativa o modo de ganho automático, deixando o driver gerenciar os ganhos.
        # Esta é a abordagem mais estável se a configuração manual estiver a falhar.
        sdr.setGainMode(SOAPY_SDR_RX, 0, True)
        logger.log(f"Modo de ganho automático ativado.", "INFO")
        
        time.sleep(0.5) # Pausa para estabilização

        # --- Fim da Configuração ---

        rxStream = sdr.setupStream(SOAPY_SDR_RX, SOAPY_SDR_CF32)
        sdr.activateStream(rxStream)
        
        time.sleep(0.1)
        
        chunk_size = 1024 * 32
        samples_buffer = np.zeros(chunk_size, np.complex64)
        total_samples_to_capture = int(sample_rate * target_info['capture_duration_seconds'])
        samples_captured = 0

        filename = f"{target_info.get('name', 'capture').replace(' ', '_')}_{timestamp}.wav"
        filepath = os.path.join("captures", filename)
        os.makedirs("captures", exist_ok=True)

        logger.log(f"Gravando por {target_info['capture_duration_seconds']}s para {filepath}...", "INFO")
        with wave.open(filepath, 'wb') as wf:
            wf.setnchannels(2)
            wf.setsampwidth(2)
            wf.setframerate(int(sample_rate))
            
            while samples_captured < total_samples_to_capture:
                sr = sdr.readStream(rxStream, [samples_buffer], len(samples_buffer), timeoutUs=int(2e6))
                if sr.ret <= 0:
                    logger.log(f"Stream SDR retornou: {sr.ret}. Verifique a conexão USB do HackRF.", "WARN")
                    continue
                chunk = samples_buffer[:sr.ret]
                samples_real = (np.real(chunk) * 32767).astype(np.int16)
                samples_imag = (np.imag(chunk) * 32767).astype(np.int16)
                stereo_chunk = np.vstack((samples_real, samples_imag)).T
                wf.writeframes(stereo_chunk.tobytes())
                samples_captured += sr.ret
    except Exception as e:
        logger.log(f"Erro CRÍTICO durante a captura: {e}", "ERROR")
    finally:
        if sdr and rxStream:
            sdr.deactivateStream(rxStream)
            sdr.closeStream(rxStream)

    if os.path.exists(filepath) and samples_captured > 0:
        logger.log(f"Sinal salvo em: {filepath}", "SUCCESS")
        
        image_path = None
        if "NOAA" in target_info.get('name', ''):
            image_path = decoder.decode_apt(filepath)
        
        db.insert_signal(
            target=target_info.get('name', 'capture'),
            frequency=frequency, 
            timestamp=timestamp, 
            filepath=filepath,
            image_path=image_path
        )