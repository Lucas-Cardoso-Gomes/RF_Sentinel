# utils/iss_post_process.py
import numpy as np
import scipy.signal as signal
from scipy.io import wavfile
import os

def fm_demod(iq_data, deviation=75000):
    """Demodula um sinal FM simples."""
    x = np.real(iq_data)
    y = np.imag(iq_data)
    
    # Derivada do sinal
    dx = np.gradient(x)
    dy = np.gradient(y)
    
    # Demodulação FM
    demodulated = (x * dy - y * dx) / (x**2 + y**2 + 1e-10)
    
    # Normaliza o resultado
    if np.max(np.abs(demodulated)) > 0:
        demodulated /= np.max(np.abs(demodulated))
        
    return demodulated

from .state_manager import AppState

def process_iss_capture(app_state: AppState, raw_filepath: str, sample_rate: int):
    """
    Lê um ficheiro RAW da ISS, procura por sinais de Voz/SSTV e APRS,
    demodula-os e salva como ficheiros de áudio separados.
    """
    try:
        app_state.log(f"Processando {raw_filepath} para sinais da ISS...", "DEBUG")
        
        # Frequências de interesse (em Hz)
        VOICE_SSTV_FREQ = 145800000
        APRS_FREQ = 145825000
        
        # Assume que a captura foi centrada na frequência de Voz/SSTV
        center_freq = VOICE_SSTV_FREQ
        
        # Calcular os desvios de frequência
        voice_offset = VOICE_SSTV_FREQ - center_freq  # 0 Hz
        aprs_offset = APRS_FREQ - center_freq      # 25000 Hz

        # Ler o ficheiro I/Q
        try:
            _, iq_raw = wavfile.read(raw_filepath)
            # Normaliza para float se for int
            if iq_raw.dtype != np.float32:
                iq_raw = iq_raw.astype(np.float32) / 128.0 - 1.0
            iq_data = (iq_raw[:, 0] + 1j * iq_raw[:, 1]).astype(np.complex64)
        except Exception as e:
            app_state.log(f"Falha ao ler o ficheiro I/Q {raw_filepath}: {e}", "ERROR")
            return

        # Parâmetros para o filtro e decimação
        audio_rate = 48000
        decimation_rate = int(sample_rate / audio_rate)
        
        # --- Processar o sinal de Voz/SSTV ---
        process_channel(app_state, iq_data, sample_rate, voice_offset, decimation_rate, raw_filepath, "_VOICE_SSTV")
        
        # --- Processar o sinal de APRS ---
        process_channel(app_state, iq_data, sample_rate, aprs_offset, decimation_rate, raw_filepath, "_APRS")

    except Exception as e:
        app_state.log(f"Falha no pós-processamento da ISS: {e}", "ERROR")

def process_channel(app_state: AppState, iq_data, sample_rate, freq_offset, decimation_rate, original_filepath, suffix):
    # 1. Deslocar a frequência de interesse para o centro (0 Hz)
    t = np.arange(len(iq_data)) / sample_rate
    iq_shifted = iq_data * np.exp(-1j * 2 * np.pi * freq_offset * t)
    
    # 2. Filtrar e decimar para a taxa de áudio
    # Cria um filtro passa-baixo para isolar o sinal
    filter_width = 15000 # Largura de 15kHz para FM estreito
    fir_filter = signal.firwin(128, filter_width / (sample_rate / 2))
    iq_filtered = signal.lfilter(fir_filter, 1.0, iq_shifted)
    
    # Decima o sinal
    iq_decimated = iq_filtered[::decimation_rate]
    
    # 3. Demodular FM
    audio_data = fm_demod(iq_decimated)
    
    # 4. Verificar se há sinal (evita guardar ficheiros de ruído)
    signal_power = np.mean(audio_data**2)
    if signal_power < 0.001:  # Limiar empírico
        app_state.log(f"Nenhum sinal significativo detetado para o canal {suffix}. Ignorando.", "INFO")
        return

    # 5. Salvar como ficheiro de áudio
    output_filename = original_filepath.replace(".wav", f"{suffix}.wav")
    audio_to_save = (audio_data * 32767).astype(np.int16)

    try:
        wavfile.write(output_filename, int(sample_rate / decimation_rate), audio_to_save)
        app_state.log(f"Áudio do canal {suffix} salvo em: {output_filename}", "SUCCESS")
    except Exception as e:
        app_state.log(f"Falha ao salvar o áudio do canal {suffix}: {e}", "ERROR")