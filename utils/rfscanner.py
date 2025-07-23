import threading
import time
import os
import uuid
import numpy as np
import SoapySDR
from scipy.io.wavfile import write as write_wav
from datetime import datetime
from backend.db import insert_signal

# --- Variáveis globais para controlar o scanner ---
scanner_active = True
scanner_thread = None

# --- NOVA FUNÇÃO DE CAPTURA REAL COM HACKRF ---
def real_capture(target_name: str, frequency: float, sample_rate: float = 2e6, gain: float = 20.0, duration_secs: int = 5):
    """
    Configura o HackRF, captura sinais por uma duração específica e salva em um arquivo WAV.
    """
    print(f"Iniciando captura real para {target_name} em {frequency / 1e6} MHz...")

    output_dir = "captures"
    os.makedirs(output_dir, exist_ok=True)

    args = dict(driver="hackrf")
    try:
        sdr = SoapySDR.Device(args)
    except Exception as e:
        print(f"ERRO: Não foi possível encontrar o HackRF. Verifique a conexão e os drivers.")
        print(f"Detalhes: {e}")
        return None

    sdr.set_sample_rate(SoapySDR.SOAPY_SDR_RX, 0, sample_rate)
    sdr.set_frequency(SoapySDR.SOAPY_SDR_RX, 0, frequency)
    sdr.set_gain(SoapySDR.SOAPY_SDR_RX, 0, gain)

    rx_stream = sdr.setup_stream(SoapySDR.SOAPY_SDR_RX, SoapySDR.SOAPY_SDR_CF32)
    sdr.activate_stream(rx_stream)

    total_samples = int(duration_secs * sample_rate)
    all_samples = np.array([], np.complex64)
    buff = np.zeros(1024, np.complex64)

    while len(all_samples) < total_samples:
        sr = sdr.read_stream(rx_stream, [buff], len(buff))
        if sr.ret > 0:
            all_samples = np.concatenate((all_samples, buff[:sr.ret]))

    sdr.deactivate_stream(rx_stream)
    sdr.close_stream(rx_stream)
    print("Captura concluída. Salvando arquivo...")

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    filename = f"{target_name}_{timestamp}.wav"
    filepath = os.path.join(output_dir, filename)

    samples_interleaved = np.empty(all_samples.size * 2, dtype=np.float32)
    samples_interleaved[0::2] = all_samples.real
    samples_interleaved[1::2] = all_samples.imag
    
    # Normaliza apenas se houver sinal, para evitar divisão por zero
    max_val = np.max(np.abs(samples_interleaved))
    if max_val > 0:
        samples_interleaved /= max_val

    write_wav(filepath, int(sample_rate), samples_interleaved.astype(np.float32))
    print(f"Arquivo salvo em: {filepath}")
    return filepath

# --- LÓGICA DO SCANNER QUE RODA EM BACKGROUND ---
def background_scanner():
    priority_targets = [
        {'name': 'ISS', 'frequency': 145.800e6},
        {'name': 'NOAA 15', 'frequency': 137.620e6},
        {'name': 'NOAA 18', 'frequency': 137.9125e6},
        {'name': 'NOAA 19', 'frequency': 137.100e6},
    ]

    while True:
        if not scanner_active:
            time.sleep(1)
            continue

        print("\n--- Iniciando novo ciclo de varredura ---")
        for target in priority_targets:
            if not scanner_active:
                print("Scanner pausado durante o ciclo.")
                break
            
            filepath = real_capture(target['name'], target['frequency'])

            if filepath:
                print(f"Registrando '{target['name']}' no banco de dados...")
                insert_signal(target['name'], target['frequency'], filepath)
            else:
                print(f"Falha na captura de '{target['name']}'. Pausando por 30 segundos...")
                time.sleep(30) # Pausa mais longa se o SDR não for encontrado

        if scanner_active:
            print("--- Ciclo de varredura concluído. Aguardando 10 segundos ---")
            time.sleep(10)

# --- FUNÇÕES DE CONTROLE (usadas pela API e inicialização) ---
def start_scanner():
    global scanner_thread
    if scanner_thread is None:
        print("Iniciando a thread do scanner em background...")
        scanner_thread = threading.Thread(target=background_scanner, daemon=True)
        scanner_thread.start()

def toggle_scanner():
    global scanner_active
    scanner_active = not scanner_active
    status = "Ativo" if scanner_active else "Parado"
    print(f"Status do Scanner alterado para: {status}")
    return scanner_active