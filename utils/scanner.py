# utils/scanner.py
import SoapySDR
from SoapySDR import *
import numpy as np
import datetime
import wave
import os
import json
import time
from scipy.signal import decimate
from utils import db, decoder
from utils.logger import logger

def perform_capture(sdr, target_info):
    rxStream = None
    filepath = ""
    timestamp = datetime.datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
    
    try:
        mode = target_info.get('mode', 'RAW')
        sample_rate = target_info.get('sample_rate', 2e6)
        frequency = target_info.get('frequency', 100e6)
        lna_gain = target_info.get("lna_gain", 32)
        vga_gain = target_info.get("vga_gain", 16)
        amp_enabled = target_info.get("amp_enabled", True)
        audio_sample_rate = 48000

        sdr.setSampleRate(SOAPY_SDR_RX, 0, sample_rate)
        sdr.setFrequency(SOAPY_SDR_RX, 0, frequency)
        rxStream = sdr.setupStream(SOAPY_SDR_RX, SOAPY_SDR_CF32)
        sdr.activateStream(rxStream)
        
        sdr.setGainMode(SOAPY_SDR_RX, 0, False)
        sdr.setGain(SOAPY_SDR_RX, 0, "LNA", lna_gain)
        sdr.setGain(SOAPY_SDR_RX, 0, "VGA", vga_gain)
        if "AMP" in sdr.listGains(SOAPY_SDR_RX, 0):
            sdr.setGain(SOAPY_SDR_RX, 0, "AMP", 1 if amp_enabled else 0)
        
        time.sleep(0.5)
        
        read_lna = sdr.getGain(SOAPY_SDR_RX, 0, "LNA")
        read_vga = sdr.getGain(SOAPY_SDR_RX, 0, "VGA")
        read_amp = sdr.getGain(SOAPY_SDR_RX, 0, "AMP") if "AMP" in sdr.listGains(SOAPY_SDR_RX, 0) else "N/A"
        logger.log(f"Ganhos Lidos -> LNA: {read_lna}dB, VGA: {read_vga}dB, AMP: {read_amp}", "SUCCESS")

        target_name = target_info.get('name', 'capture')
        filename = f"{target_name.replace(' ', '_')}_{timestamp}_{mode}.wav"
        filepath = os.path.join("captures", filename)
        os.makedirs("captures", exist_ok=True)
        
        logger.log(f"Gravando {target_name} em modo {mode} por {target_info['capture_duration_seconds']}s...", "INFO")

        with wave.open(filepath, 'wb') as wf:
            if mode == 'RAW':
                wf.setnchannels(2); wf.setsampwidth(2); wf.setframerate(int(sample_rate))
            else:
                wf.setnchannels(1); wf.setsampwidth(2); wf.setframerate(audio_sample_rate)

            total_samples_to_capture = int(sample_rate * target_info['capture_duration_seconds'])
            samples_captured = 0
            chunk_size = 1024 * 128 if sample_rate > 5e6 else 1024 * 16
            samples_buffer = np.zeros(chunk_size, np.complex64)

            while samples_captured < total_samples_to_capture:
                sr = sdr.readStream(rxStream, [samples_buffer], len(samples_buffer), timeoutUs=int(2e6))
                if sr.ret <= 0:
                    logger.log(f"Stream SDR retornou: {sr.ret}. Verifique a conexão USB.", "WARN")
                    continue
                
                chunk = samples_buffer[:sr.ret]

                if mode == 'RAW':
                    samples_real = (np.real(chunk) * 32767).astype(np.int16)
                    samples_imag = (np.imag(chunk) * 32767).astype(np.int16)
                    output_chunk = np.vstack((samples_real, samples_imag)).T
                else:
                    if mode == 'FM': x = np.diff(np.unwrap(np.angle(chunk)))
                    else: x = np.abs(chunk) # AM
                    decimation_factor = int(sample_rate / audio_sample_rate)
                    if decimation_factor > 1: x = decimate(x, decimation_factor)
                    x /= np.max(np.abs(x)) if np.max(np.abs(x)) > 0 else 1
                    output_chunk = (x * 32767).astype(np.int16)
                
                wf.writeframes(output_chunk.tobytes())
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
        if "NOAA" in target_info.get('name', '') and mode == 'RAW':
            image_path = decoder.decode_apt(filepath)
        
        db.insert_signal(
            target=target_info.get('name', 'capture'),
            frequency=frequency, 
            timestamp=timestamp, 
            filepath=filepath,
            image_path=image_path
        )