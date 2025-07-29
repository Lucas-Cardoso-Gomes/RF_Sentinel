# utils/decoder.py
import numpy as np
from scipy.signal import hilbert, resample, correlate
from scipy.io import wavfile
from PIL import Image
import os
from utils.logger import logger

# --- Constantes para o sinal APT ---
APT_LINE_RATE_HZ = 2.0  # 2 linhas por segundo
APT_SYNC_FRAME_DURATION_MS = 47  # Duração do quadro de sincronização A
APT_SYNC_A_FREQ = 1040  # Frequência da portadora do Sync A (Hz)
IMAGE_WIDTH_PX = 909    # Largura padrão para imagens APT (imagem A ou B)

def decode_apt(wav_filepath: str) -> str | None:
    """
    Decodifica um arquivo WAV contendo um sinal APT de um satélite NOAA.
    Utiliza correlação cruzada para uma sincronização robusta das linhas da imagem.
    """
    logger.log(f"🛰️  Iniciando decodificação APT para: {wav_filepath}", "INFO")
    try:
        # 1. Carregar o arquivo WAV
        samplerate, signal_stereo = wavfile.read(wav_filepath)
        signal = signal_stereo[:, 0].astype(np.float32)

        # 2. Demodulação AM usando a transformada de Hilbert
        logger.log("    -> Realizando demodulação AM...", "DEBUG")
        analytic_signal = hilbert(signal)
        am_demodulated = np.abs(analytic_signal)

        # 3. Reamostragem para uma taxa de amostragem mais gerenciável (melhora performance)
        resampling_rate = 20800  # 5x a taxa de linha, bom para performance
        logger.log(f"    -> Reamostrando de {samplerate} Hz para {resampling_rate} Hz...", "DEBUG")
        num_samples_resampled = int(len(am_demodulated) * resampling_rate / samplerate)
        resampled_signal = resample(am_demodulated, num_samples_resampled)

        # Normalizar o sinal entre -1 e 1 para a correlação
        resampled_signal = resampled_signal / np.max(np.abs(resampled_signal))

        # 4. Gerar o Padrão de Sincronização (Sync A)
        sync_a_len = int(resampling_rate * APT_SYNC_FRAME_DURATION_MS / 2000)
        t_sync = np.linspace(0, (sync_a_len-1)/resampling_rate, sync_a_len, endpoint=False)
        # 7 pulsos de onda quadrada a 1040 Hz
        sync_a_pattern = np.sign(np.sin(2 * np.pi * APT_SYNC_A_FREQ * t_sync))

        # 5. Sincronização por Correlação Cruzada
        logger.log("    -> Sincronizando linhas via correlação cruzada...", "INFO")
        correlation = correlate(resampled_signal, sync_a_pattern, mode='same')
        
        # Encontrar picos na correlação
        line_width_samples = int(resampling_rate / APT_LINE_RATE_HZ)
        peaks = []
        for i in range(0, len(correlation), line_width_samples):
            segment = correlation[i : i + line_width_samples]
            if len(segment) > 0:
                peak_index = np.argmax(segment)
                # Verifica se o pico é significativo (threshold simples)
                if segment[peak_index] > 0.1 * np.max(correlation):
                    peaks.append(i + peak_index)

        if not peaks:
            logger.log("❌ Erro: Nenhum quadro de sincronização válido encontrado.", "ERROR")
            return None
        
        logger.log(f"    -> {len(peaks)} linhas de imagem detectadas.", "DEBUG")

        # 6. Construir a Imagem
        image_matrix = np.zeros((len(peaks), IMAGE_WIDTH_PX), dtype=np.uint8)
        
        # Largura da imagem em amostras na taxa de amostragem atual
        image_width_samples = int(line_width_samples / 2) 

        for i, peak_start in enumerate(peaks):
            line_start = peak_start
            line_end = line_start + image_width_samples
            if line_end > len(resampled_signal):
                break # Evita ler além do final do sinal
            
            line_data = resampled_signal[line_start:line_end]

            # Redimensionar a linha para a largura final da imagem
            # O Pillow/Numpy lida com isso de forma eficiente
            temp_img = Image.fromarray(line_data.reshape(1, -1))
            resized_line = temp_img.resize((IMAGE_WIDTH_PX, 1), Image.Resampling.LANCZOS)
            
            image_matrix[i, :] = np.array(resized_line)

        # Normaliza a matriz final para 0-255
        pixels = (image_matrix - np.min(image_matrix)) / (np.max(image_matrix) - np.min(image_matrix)) * 255
        pixels = pixels.astype(np.uint8)
        
        img_final = Image.fromarray(pixels)

        # 7. Salvar a imagem
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