# utils/scanner.py
import subprocess
import SoapySDR
from SoapySDR import *
import numpy as np
import datetime
import wave
import os
import json
import time
from scipy.signal import decimate
# A linha que causava o erro foi removida.
# A importação agora é apenas dos módulos necessários do seu projeto.
from utils import db, decoder
from utils.logger import logger

def perform_capture(sdr, target_info):
    """
    Executa a captura de sinal utilizando a ferramenta de linha de comandos hackrf_transfer
    para máxima estabilidade e para contornar problemas de driver com SoapySDR.
    """
    filepath = ""
    timestamp = datetime.datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
    
    try:
        # --- Parâmetros ---
        mode = target_info.get('mode', 'RAW')
        sample_rate = int(target_info.get('sample_rate', 2e6))
        frequency = int(target_info.get('frequency', 100e6))
        lna_gain = target_info.get("lna_gain", 40)
        vga_gain = target_info.get("vga_gain", 30)
        amp_enabled = target_info.get("amp_enabled", True)
        duration_sec = target_info['capture_duration_seconds']
        
        if sdr:
            logger.log("Dispositivo SDR libertado para permitir o uso pelo hackrf_transfer.", "DEBUG")

        # --- Geração do Nome do Ficheiro ---
        target_name = target_info.get('name', 'capture')
        
        raw_filename = f"{target_name.replace(' ', '_')}_{timestamp}.iq"
        raw_filepath = os.path.join("captures", raw_filename)
        os.makedirs("captures", exist_ok=True)
        
        # --- Construção do Comando hackrf_transfer ---
        command_list = [
            'hackrf_transfer',
            '-r', raw_filepath,
            '-f', str(frequency),
            '-s', str(sample_rate),
            '-l', str(lna_gain),
            '-g', str(vga_gain),
            '-n', str(int(sample_rate * duration_sec))
        ]
        if amp_enabled:
            command_list.append('-a')
            command_list.append('1')
        
        command_str = ' '.join(command_list)
            
        logger.log(f"A executar comando externo: {command_str}", "INFO")
        
        # --- Execução do Comando ---
        process = subprocess.Popen(command_str, shell=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        stdout, stderr = process.communicate()
        
        if process.returncode != 0:
            logger.log(f"Erro ao executar hackrf_transfer: {stderr.decode('utf-8', errors='ignore')}", "ERROR")
            return
            
        logger.log("Captura com hackrf_transfer concluída com sucesso.", "SUCCESS")

        # --- Conversão do Ficheiro .iq para .wav ---
        if os.path.exists(raw_filepath):
            logger.log(f"A converter {raw_filepath} para formato .wav...", "INFO")
            
            iq_data = np.fromfile(raw_filepath, dtype=np.int8)
            iq_data_float = iq_data.astype(np.float32) / 128.0
            complex_data = iq_data_float[0::2] + 1j * iq_data_float[1::2]
            
            os.remove(raw_filepath)

            # --- Lógica de Demodulação e Gravação ---
            final_filename = f"{target_name.replace(' ', '_')}_{timestamp}_{mode}.wav"
            filepath = os.path.join("captures", final_filename)

            with wave.open(filepath, 'wb') as wf:
                if mode == 'RAW':
                    wf.setnchannels(2); wf.setsampwidth(2); wf.setframerate(int(sample_rate))
                    samples_real = (np.real(complex_data) * 32767).astype(np.int16)
                    samples_imag = (np.imag(complex_data) * 32767).astype(np.int16)
                    output_chunk = np.vstack((samples_real, samples_imag)).T
                else: # AM ou FM
                    audio_sample_rate = 48000
                    wf.setnchannels(1); wf.setsampwidth(2); wf.setframerate(audio_sample_rate)
                    if mode == 'FM': x = np.diff(np.unwrap(np.angle(complex_data)))
                    else: x = np.abs(complex_data)
                    decimation_factor = int(sample_rate / audio_sample_rate)
                    if decimation_factor > 1: x = decimate(x, decimation_factor)
                    x /= np.max(np.abs(x)) if np.max(np.abs(x)) > 0 else 1
                    output_chunk = (x * 32767).astype(np.int16)
                
                wf.writeframes(output_chunk.tobytes())
            
            logger.log(f"Sinal salvo em: {filepath}", "SUCCESS")
            image_path = None
            if "NOAA" in target_name and mode == 'RAW':
                image_path = decoder.decode_apt(filepath)
            
            db.insert_signal(
                target=target_name,
                frequency=frequency, 
                timestamp=timestamp, 
                filepath=filepath,
                image_path=image_path
            )

    except Exception as e:
        logger.log(f"Erro CRÍTICO durante a captura externa: {e}", "ERROR")