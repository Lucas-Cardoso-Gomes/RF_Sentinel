# utils/decoder.py
import numpy as np
from scipy.signal import hilbert, resample, correlate
import wave 
from PIL import Image
import os
from utils.logger import logger

# --- Constantes para o sinal APT ---
APT_LINE_RATE_HZ = 2.0
APT_SYNC_FRAME_DURATION_MS = 47
APT_SYNC_A_FREQ = 1040
IMAGE_WIDTH_PX = 909

def decode_apt(wav_filepath: str) -> str | None:
    """
    Decodifica um arquivo WAV contendo um sinal APT de um satélite NOAA.
    Utiliza correlação cruzada e processamento em chunks para economizar memória.
    """
    logger.log(f"🛰️  Iniciando decodificação APT para: {wav_filepath}", "INFO")
    try:
        resampled_chunks = []
        resampling_rate = 20800

        with wave.open(wav_filepath, 'rb') as wf:
            samplerate = wf.getframerate()
            num_frames = wf.getnframes()
            chunk_size_frames = samplerate 
            
            logger.log("    -> Processando áudio em chunks para economizar memória...", "DEBUG")
            for i in range(0, num_frames, chunk_size_frames):
                frames = wf.readframes(chunk_size_frames)
                if not frames:
                    break
                
                signal_stereo = np.frombuffer(frames, dtype=np.int16)
                
                if len(signal_stereo) % 2 != 0:
                    signal_stereo = signal_stereo[:-1]
                
                signal_stereo = signal_stereo.reshape(-1, 2)
                signal = signal_stereo[:, 0].astype(np.float32)

                analytic_signal = hilbert(signal)
                am_demodulated = np.abs(analytic_signal)

                num_samples_resampled = int(len(am_demodulated) * resampling_rate / samplerate)
                resampled_chunk = resample(am_demodulated, num_samples_resampled)
                resampled_chunks.append(resampled_chunk)

        logger.log("    -> Montando sinal reamostrado...", "DEBUG")
        resampled_signal = np.concatenate(resampled_chunks)
        
        if np.max(np.abs(resampled_signal)) > 0:
            resampled_signal = resampled_signal / np.max(np.abs(resampled_signal))

        sync_a_len = int(resampling_rate * APT_SYNC_FRAME_DURATION_MS / 2000)
        t_sync = np.linspace(0, (sync_a_len - 1) / resampling_rate, sync_a_len, endpoint=False)
        sync_a_pattern = np.sign(np.sin(2 * np.pi * APT_SYNC_A_FREQ * t_sync))

        logger.log("    -> Sincronizando linhas via correlação cruzada...", "INFO")
        correlation = correlate(resampled_signal, sync_a_pattern, mode='same')
        
        line_width_samples = int(resampling_rate / APT_LINE_RATE_HZ)
        peaks = []
        correlation_max = np.max(correlation)
        # Adiciona uma verificação para garantir que correlation_max não seja zero
        if correlation_max > 0:
            for i in range(0, len(correlation), line_width_samples):
                segment = correlation[i : i + line_width_samples]
                if len(segment) > 0:
                    peak_index = np.argmax(segment)
                    if segment[peak_index] > 0.1 * correlation_max:
                        peaks.append(i + peak_index)

        if not peaks:
            logger.log("❌ Erro: Nenhum quadro de sincronização válido encontrado.", "ERROR")
            return None
        
        logger.log(f"    -> {len(peaks)} linhas de imagem detectadas.", "DEBUG")

        image_matrix = np.zeros((len(peaks), IMAGE_WIDTH_PX), dtype=np.float32)
        image_width_samples = int(line_width_samples / 2) 

        for i, peak_start in enumerate(peaks):
            line_start = peak_start
            line_end = line_start + image_width_samples
            if line_end > len(resampled_signal):
                break
            
            line_data = resampled_signal[line_start:line_end]
            temp_img = Image.fromarray(line_data.reshape(1, -1))
            resized_line = temp_img.resize((IMAGE_WIDTH_PX, 1), Image.Resampling.LANCZOS)
            image_matrix[i, :] = np.array(resized_line)

        # --- CORREÇÃO: Verifica se a imagem não é uma cor sólida antes de normalizar ---
        min_val = np.min(image_matrix)
        max_val = np.max(image_matrix)
        
        # A normalização só é feita se houver variação nos valores dos pixels
        if (max_val - min_val) > 1e-6: # Um valor pequeno para evitar problemas de ponto flutuante
            pixels = (image_matrix - min_val) / (max_val - min_val) * 255.0
            pixels = pixels.astype(np.uint8)
        else:
            # Se a imagem for de cor sólida, cria uma imagem preta
            pixels = np.zeros_like(image_matrix, dtype=np.uint8)
        # --- FIM DA CORREÇÃO ---
        
        img_final = Image.fromarray(pixels)

        output_dir = os.path.join("captures", "images")
        os.makedirs(output_dir, exist_ok=True)
        base_filename = os.path.splitext(os.path.basename(wav_filepath))[0]
        output_filepath = os.path.join(output_dir, f"{base_filename}.png")
        
        img_final.save(output_filepath)
        logger.log(f"✅ Imagem APT salva em: {output_filepath}", "SUCCESS")
        return output_filepath

    except Exception as e:
        logger.log(f"❌ Falha na decodificação APT: {e}", "ERROR")
        return None