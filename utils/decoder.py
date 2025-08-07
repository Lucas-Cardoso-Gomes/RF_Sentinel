# utils/decoder.py
import numpy as np
from PIL import Image, ImageOps
from scipy.signal import hilbert, resample, correlate
import os
from utils.logger import logger

# --- Constantes Otimizadas para APT ---
APT_LINE_RATE_HZ = 2.0
APT_SYNC_A_FREQ = 1040
IMAGE_WIDTH_PX = 909
PROCESSING_RATE = 11025 * 2

class RealtimeAPTDecoder:
    def __init__(self, wav_filepath, original_samplerate):
        self.wav_filepath = wav_filepath
        self.original_samplerate = original_samplerate
        self.processing_rate = PROCESSING_RATE
        self.line_width_samples = int(self.processing_rate / APT_LINE_RATE_HZ)
        self.sync_pattern = self._generate_sync_pattern()
        self.image_matrix = []
        self._buffer = np.array([], dtype=np.float32)
        # CORREÇÃO: Adiciona um limiar para a detecção de picos de sincronização
        self.correlation_threshold = 5 
        logger.log("Decodificador em tempo real iniciado.", "DEBUG")

    def _generate_sync_pattern(self):
        sync_pulse_samples = int(0.005 * self.processing_rate)
        t_sync = np.arange(sync_pulse_samples) / self.processing_rate
        return np.sin(2 * np.pi * APT_SYNC_A_FREQ * t_sync)

    def process_chunk(self, complex_chunk):
        am_demodulated = np.abs(complex_chunk)

        num_samples_resampled = int(len(am_demodulated) * self.processing_rate / self.original_samplerate)
        resampled_chunk = resample(am_demodulated, num_samples_resampled)
        
        if np.max(resampled_chunk) > 0:
            resampled_chunk /= np.max(resampled_chunk)

        self._buffer = np.concatenate([self._buffer, resampled_chunk])

        while len(self._buffer) >= self.line_width_samples:
            line_data = self._buffer[:self.line_width_samples]
            self._buffer = self._buffer[self.line_width_samples:]
            
            self._process_line(line_data)

    def _process_line(self, line_data):
        # CORREÇÃO: Aplica um filtro de média móvel para suavizar o sinal antes da correlação
        window_size = 10
        line_data_smooth = np.convolve(line_data, np.ones(window_size)/window_size, mode='same')

        correlation = correlate(line_data_smooth, self.sync_pattern, mode='valid')
        
        peak = np.argmax(correlation)
        peak_value = correlation[peak]

        # CORREÇÃO: Verifica se o pico encontrado é forte o suficiente (acima do ruído)
        if peak_value < self.correlation_threshold:
            return # Ignora a linha se a sincronização for fraca

        image_data_length = int(self.line_width_samples / 2) 
        line_end = peak + image_data_length
        
        if line_end > len(line_data):
            return

        image_line_data = line_data[peak:line_end]
        
        line_scaled = (image_line_data * 255).astype(np.uint8)
        line_img = Image.fromarray(line_scaled.reshape(1, -1))
        corrected_line = line_img.resize((IMAGE_WIDTH_PX, 1), Image.Resampling.LANCZOS)
        
        self.image_matrix.append(np.array(corrected_line))

    def finalize(self):
        if not self.image_matrix:
            logger.log("Nenhuma linha de imagem foi decodificada. Imagem não será salva.", "WARN")
            return None
        
        logger.log(f"Finalizando imagem com {len(self.image_matrix)} linhas.", "INFO")
        final_matrix = np.vstack(self.image_matrix)
        
        img_final = Image.fromarray(final_matrix)
        img_final = ImageOps.equalize(img_final)

        output_dir = os.path.join("captures", "images")
        os.makedirs(output_dir, exist_ok=True)
        base_filename = os.path.splitext(os.path.basename(self.wav_filepath))[0]
        output_filepath = os.path.join(output_dir, f"{base_filename}.png")
        
        img_final.save(output_filepath)
        logger.log(f"✅ Imagem APT aprimorada salva em: {output_filepath}", "SUCCESS")
        return output_filepath