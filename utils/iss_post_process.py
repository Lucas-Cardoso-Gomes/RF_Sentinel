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

def process_iss_capture(raw_filepath, sample_rate, logger):
    """
    Lê um ficheiro RAW da ISS, procura por sinais de Voz/SSTV e APRS,
    demodula-os e salva como ficheiros de áudio separados.
    """
    try:
        logger.log(f"A processar {raw_filepath}...", "DEBUG")
        
        # Frequências de interesse (em Hz)
        VOICE_SSTV_FREQ = 145800000
        APRS_FREQ = 145825000
        
        # Frequência central da captura (obtida do nome do ficheiro, se necessário, ou assumida)
        # Por agora, vamos assumir que foi centrado em 145.800 MHz
        center_freq = 145800000 
        
        # Calcular os desvios de frequência
        voice_offset = VOICE_SSTV_FREQ - center_freq # Deverá ser 0
        aprs_offset = APRS_FREQ - center_freq   # Deverá ser 25000

        # Ler o ficheiro I/Q
        _, iq_raw = wavfile.read(raw_filepath)
        iq_data = (iq_raw[:, 0] + 1j * iq_raw[:, 1]).astype(np.complex64)

        # Parâmetros para o filtro e decimação
        audio_rate = 48000
        decimation_rate = int(sample_rate / audio_rate)
        
        # --- Processar o sinal de Voz/SSTV ---
        process_channel(iq_data, sample_rate, voice_offset, decimation_rate, raw_filepath, "_VOICE_SSTV", logger)
        
        # --- Processar o sinal de APRS ---
        process_channel(iq_data, sample_rate, aprs_offset, decimation_rate, raw_filepath, "_APRS", logger)

    except Exception as e:
        logger.log(f"Falha no pós-processamento da ISS: {e}", "ERROR")

def process_channel(iq_data, sample_rate, freq_offset, decimation_rate, original_filepath, suffix, logger):
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
    
    # 4. Verificar se há sinal (evita guardar ficheiros de ruído puro)
    # Uma heurística simples: verifica se a energia do sinal é maior que um limiar
    signal_power = np.mean(audio_data**2)
    if signal_power < 0.001: # Limiar ajustável
        logger.log(f"Nenhum sinal significativo detetado para o canal {suffix}. A ignorar.", "INFO")
        return

    # 5. Salvar como ficheiro de áudio
    output_filename = original_filepath.replace(".wav", f"{suffix}.wav")
    audio_to_save = (audio_data * 32767).astype(np.int16)
    wavfile.write(output_filename, int(sample_rate / decimation_rate), audio_to_save)
    logger.log(f"Áudio do canal {suffix} salvo em: {output_filename}", "SUCCESS")