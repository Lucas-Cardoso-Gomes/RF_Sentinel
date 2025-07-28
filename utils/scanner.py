# utils/scanner.py
import SoapySDR
from SoapySDR import *
import numpy as np
import datetime
import os
import json
import time
import wave # Módulo nativo para escrever o .wav em streaming
from utils import db, decoder
from .sdr_manager import sdr_manager

def check_hardware_status():
    """Verifica se o HackRF pode ser encontrado, sem abrir a conexão."""
    if sdr_manager.find_hackrf():
        return True, "HackRF One Conectado"
    else:
        return False, "HackRF One Não Encontrado"

def load_config():
    """Carrega as configurações do arquivo JSON."""
    with open("config.json", "r") as f:
        return json.load(f)

def apply_gain_settings(sdr, gains):
    """Aplica as configurações de ganho LNA, VGA e AMP ao dispositivo SDR."""
    if sdr and gains:
        if "lna" in gains: sdr.setGain(SOAPY_SDR_RX, 0, "LNA", gains["lna"])
        if "vga" in gains: sdr.setGain(SOAPY_SDR_RX, 0, "VGA", gains["vga"])
        if "amp" in gains: sdr.setGain(SOAPY_SDR_RX, 0, "AMP", gains["amp"])
        print(f"    -> Ganhos configurados: LNA={gains.get('lna', 'N/A')}, VGA={gains.get('vga', 'N/A')}")

# A função de monitoramento não precisa de streaming, pois já lê em pequenos pedaços
def monitor_amateur_radio(duration_seconds: int, scanner_event):
    # (Esta função pode permanecer como está na versão anterior)
    pass

def real_capture(target_info):
    """
    Configura o SDR e captura o sinal em streaming para um arquivo WAV,
    evitando o uso excessivo de memória.
    """
    sdr = sdr_manager.acquire_device()
    if not sdr:
        print("❌ Não foi possível adquirir o SDR para captura.")
        return

    config = load_config()
    sdr_settings = config['sdr_settings']
    rxStream = None
    
    timestamp = datetime.datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
    filename = f"{target_info['name'].replace(' ', '_')}_{timestamp}.wav"
    filepath = os.path.join("captures", filename)
    os.makedirs("captures", exist_ok=True)

    try:
        sample_rate = sdr_settings['sample_rate']
        sdr.setSampleRate(SOAPY_SDR_RX, 0, sample_rate)
        sdr.setFrequency(SOAPY_SDR_RX, 0, target_info['frequency'])
        apply_gain_settings(sdr, target_info.get("gains"))
        
        rxStream = sdr.setupStream(SOAPY_SDR_RX, SOAPY_SDR_CF32)
        sdr.activateStream(rxStream)
        sdr_manager.active_stream = rxStream
        
        # --- LÓGICA DE STREAMING ---
        chunk_size = 1024 * 16 # Tamanho do buffer para cada leitura
        samples_buffer = np.zeros(chunk_size, np.complex64)
        total_samples_to_capture = int(sample_rate * target_info['capture_duration_seconds'])
        samples_captured = 0

        print(f"    -> Gravando por {target_info['capture_duration_seconds']} segundos para {filepath}...")

        with wave.open(filepath, 'wb') as wf:
            wf.setnchannels(2) # Estéreo para I/Q
            wf.setsampwidth(2) # 2 bytes para int16
            wf.setframerate(int(sample_rate))
            
            while samples_captured < total_samples_to_capture:
                sr = sdr.readStream(rxStream, [samples_buffer], len(samples_buffer))
                if sr.ret <= 0:
                    print(f"⚠️ Alerta: readStream retornou {sr.ret}. Pode ter havido perda de amostras.")
                    continue
                
                # Processa o chunk lido
                chunk = samples_buffer[:sr.ret]
                samples_real = (np.real(chunk) * 32767).astype(np.int16)
                samples_imag = (np.imag(chunk) * 32767).astype(np.int16)
                stereo_chunk = np.vstack((samples_real, samples_imag)).T
                
                # Escreve o chunk processado no arquivo .wav
                wf.writeframes(stereo_chunk.tobytes())
                samples_captured += sr.ret

    except Exception as e:
        print(f"❌ Erro durante a captura com SDR: {e}")
    finally:
        if sdr and rxStream:
            sdr.deactivateStream(rxStream)
            sdr.closeStream(rxStream)
            sdr_manager.active_stream = None
        sdr_manager.release_device()

    print(f"💾 Sinal salvo em: {filepath}")
    db.insert_signal(
        target=target_info['name'],
        frequency=target_info['frequency'],
        timestamp=timestamp,
        filepath=filepath,
    )

    if "NOAA" in target_info['name']:
        decoder.decode_apt(filepath)