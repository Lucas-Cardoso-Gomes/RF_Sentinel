# utils/decoder.py
import numpy as np
import wave
from PIL import Image, ImageOps
from scipy.signal import hilbert, resample, correlate
import os
from utils.logger import logger

# --- Constantes Otimizadas para APT ---
APT_LINE_RATE_HZ = 2.0
APT_SYNC_A_FREQ = 1040
IMAGE_WIDTH_PX = 909  # Largura padrão para a imagem do sensor A
PROCESSING_RATE = 11025 * 2 # Taxa de amostragem interna para processamento eficiente

def decode_apt(wav_filepath: str) -> str | None:
    """
    Decodifica um ficheiro WAV de satélite NOAA com alta qualidade, aplicando:
    1. Processamento em Chunks para economizar memória.
    2. Sincronização robusta com correlação cruzada.
    3. Correção de Inclinação (Slant Correction) para nitidez.
    4. Equalização de Histograma para melhoria de contraste.
    """
    logger.log(f"🛰️  Iniciando decodificação APT avançada para: {wav_filepath}", "INFO")
    try:
        # --- 1. Leitura e Pré-processamento em Chunks ---
        resampled_chunks = []
        with wave.open(wav_filepath, 'rb') as wf:
            samplerate = wf.getframerate()
            num_frames = wf.getnframes()
            chunk_size = samplerate  # Processa 1 segundo de áudio de cada vez

            logger.log("    -> 1/5: Processando áudio em chunks...", "DEBUG")
            for i in range(0, num_frames, chunk_size):
                frames = wf.readframes(chunk_size)
                if not frames: break
                
                signal_stereo = np.frombuffer(frames, dtype=np.int16).reshape(-1, 2)
                signal = signal_stereo[:, 0].astype(np.float32)

                am_demodulated = np.abs(hilbert(signal))

                num_samples_resampled = int(len(am_demodulated) * PROCESSING_RATE / samplerate)
                resampled_chunk = resample(am_demodulated, num_samples_resampled)
                resampled_chunks.append(resampled_chunk)

        resampled_signal = np.concatenate(resampled_chunks)
        if np.max(resampled_signal) > 0:
            resampled_signal /= np.max(resampled_signal)

        # --- 2. Geração do Padrão de Sincronização e Filtragem ---
        logger.log("    -> 2/5: Gerando padrão de sincronização...", "DEBUG")
        sync_pulse_samples = int(0.005 * PROCESSING_RATE) # Pulso de 5ms
        t_sync = np.arange(sync_pulse_samples) / PROCESSING_RATE
        sync_pattern = np.sin(2 * np.pi * APT_SYNC_A_FREQ * t_sync)
        
        # Filtro de média móvel para suavizar o sinal
        window_size = 10
        resampled_signal = np.convolve(resampled_signal, np.ones(window_size)/window_size, mode='same')

        # --- 3. Sincronização por Correlação Cruzada ---
        logger.log("    -> 3/5: Sincronizando linhas via correlação cruzada...", "INFO")
        correlation = correlate(resampled_signal, sync_pattern, mode='valid')
        
        line_width = int(PROCESSING_RATE / APT_LINE_RATE_HZ)
        peaks = []
        for i in range(0, len(correlation), line_width):
            segment = correlation[i : i + line_width]
            if len(segment) > 0:
                peaks.append(i + np.argmax(segment))

        if len(peaks) < 10: # Requer um número mínimo de linhas para uma imagem válida
            logger.log("❌ Erro: Sincronização falhou. Poucas linhas de imagem encontradas.", "ERROR")
            return None
        logger.log(f"    -> {len(peaks)} linhas de imagem detectadas.", "DEBUG")

        # --- 4. Correção de Inclinação (Slant Correction) ---
        logger.log("    -> 4/5: Aplicando correção de inclinação para nitidez...", "INFO")
        
        # Calcula o comprimento médio real da linha com base nos picos
        avg_line_length = np.mean(np.diff(peaks))
        image_data_length = int(avg_line_length / 2) # A imagem ocupa metade da linha

        matrix = np.zeros((len(peaks) - 1, IMAGE_WIDTH_PX), dtype=np.uint8)

        for i in range(len(peaks) - 1):
            line_start = peaks[i]
            line_end = line_start + image_data_length
            
            if line_end > len(resampled_signal): break
            
            line = resampled_signal[line_start:line_end]
            
            # Converte a linha para uma imagem Pillow e redimensiona para o tamanho padrão
            # Este passo corrige a inclinação
            line_img = Image.fromarray(line.reshape(1, -1))
            corrected_line = line_img.resize((IMAGE_WIDTH_PX, 1), Image.Resampling.LANCZOS)
            
            matrix[i, :] = np.array(corrected_line)
        
        # --- 5. Finalização e Melhoria de Contraste ---
        logger.log("    -> 5/5: Melhorando contraste e salvando imagem final...", "INFO")
        
        img_final = Image.fromarray(matrix)
        
        # Aplica a equalização de histograma para melhorar o contraste
        img_final = ImageOps.equalize(img_final)

        # --- Salvamento do Ficheiro ---
        output_dir = os.path.join("captures", "images")
        os.makedirs(output_dir, exist_ok=True)
        base_filename = os.path.splitext(os.path.basename(wav_filepath))[0]
        output_filepath = os.path.join(output_dir, f"{base_filename}.png")
        
        img_final.save(output_filepath)
        logger.log(f"✅ Imagem APT aprimorada salva em: {output_filepath}", "SUCCESS")
        return output_filepath

    except Exception as e:
        logger.log(f"❌ Falha na decodificação APT avançada: {e}", "ERROR")
        return None