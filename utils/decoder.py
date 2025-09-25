import numpy as np
from PIL import Image, ImageOps
from scipy.signal import resample, correlate, find_peaks, firwin, lfilter
import os
from .state_manager import AppState

# --- Constantes Otimizadas para APT ---
APT_LINE_RATE_HZ = 2.0
APT_SYNC_A_FREQ = 1040
IMAGE_WIDTH_PX = 909
PROCESSING_RATE = 22050

class RealtimeAPTDecoder:
    def __init__(self, app_state: AppState, wav_filepath: str, original_samplerate: int, force_decode: bool = False):
        self.app_state = app_state
        self.wav_filepath = wav_filepath
        self.original_samplerate = original_samplerate
        self.force_decode = force_decode
        self.processing_rate = PROCESSING_RATE
        self.nominal_line_width = int(self.processing_rate / APT_LINE_RATE_HZ)
        self.sync_pattern = self._generate_sync_pattern()
        self.image_matrix = []
        self._buffer = np.array([], dtype=np.float32)
        self.processing_chunk_size = self.processing_rate * 20

        # Cria o filtro de ruído (low-pass filter)
        cutoff_hz = 5000.0
        num_taps = 128
        self.noise_filter = firwin(num_taps, cutoff_hz / (original_samplerate / 2))

    def _generate_sync_pattern(self):
        num_cycles = 7
        samples_per_cycle = self.processing_rate / APT_SYNC_A_FREQ
        sync_pulse_samples = int(num_cycles * samples_per_cycle)
        t_sync = np.arange(sync_pulse_samples) / self.processing_rate
        return np.sin(2 * np.pi * APT_SYNC_A_FREQ * t_sync)

    def process_chunk(self, complex_chunk):
        am_demodulated = np.abs(complex_chunk)
        am_filtered = lfilter(self.noise_filter, 1.0, am_demodulated)
        num_samples_resampled = int(len(am_filtered) * self.processing_rate / self.original_samplerate)
        resampled_chunk = resample(am_filtered, num_samples_resampled)
        
        if np.max(resampled_chunk) > 0:
            resampled_chunk /= np.max(resampled_chunk)

        self._buffer = np.concatenate([self._buffer, resampled_chunk])

        while len(self._buffer) >= self.processing_chunk_size:
            chunk_to_process = self._buffer[:self.processing_chunk_size]
            self._buffer = self._buffer[self.processing_chunk_size:]
            self._find_and_process_lines(chunk_to_process)

    def _find_and_process_lines(self, data_chunk):
        self.app_state.log(f"Processando bloco de {len(data_chunk)/self.processing_rate:.1f}s para encontrar ritmo...", "DEBUG")
        
        correlation = correlate(data_chunk, self.sync_pattern, mode='valid')
        
        corr_peak_val = np.max(correlation)
        if corr_peak_val < 1.0: return
            
        peaks, _ = find_peaks(
            correlation, 
            height=corr_peak_val * 0.5,
            distance=self.nominal_line_width * 0.9
        )

        if len(peaks) < 3:
            self.app_state.log("Picos de sincronização insuficientes no bloco.", "WARN")
            return

        intervals = np.diff(peaks)
        median_interval = np.median(intervals)

        # Validação do ritmo do sinal para evitar processamento de ruído.
        if not self.force_decode and not (self.nominal_line_width * 0.75 < median_interval < self.nominal_line_width * 1.25):
            self.app_state.log(f"Ritmo de sinal anômalo (mediana: {median_interval:.2f}). Ignorando bloco.", "WARN")
            return
        elif self.force_decode:
            self.app_state.log(f"Forçando decodificação com ritmo instável (mediana: {median_interval:.2f}).", "WARN")

        effective_line_width = int(median_interval)
        self.app_state.log(f"Sincronização OK! {len(peaks)} linhas com ritmo de {effective_line_width} amostras.", "INFO")
        
        image_samples_per_line = int(0.436 * effective_line_width)
        
        for peak_start in peaks:
            start_of_image = peak_start + len(self.sync_pattern)
            end_of_image = start_of_image + image_samples_per_line

            if end_of_image > len(data_chunk): continue
            
            image_line_data = data_chunk[start_of_image:end_of_image]
            
            min_val, max_val = np.min(image_line_data), np.max(image_line_data)
            if max_val > min_val:
                image_line_data = (image_line_data - min_val) / (max_val - min_val)

            line_scaled = (image_line_data * 255).astype(np.uint8)
            line_img = Image.fromarray(line_scaled.reshape(1, -1), 'L')
            corrected_line = line_img.resize((IMAGE_WIDTH_PX, 1), Image.Resampling.LANCZOS)
            self.image_matrix.append(np.array(corrected_line))

    def finalize(self):
        # Processa qualquer dado restante no buffer.
        if len(self._buffer) > self.nominal_line_width:
            self._find_and_process_lines(self._buffer)
        
        if not self.image_matrix:
            self.app_state.log("Nenhuma linha de imagem válida foi decodificada. Imagem não será salva.", "WARN")
            return None
        
        self.app_state.log(f"Finalizando imagem com {len(self.image_matrix)} linhas.", "INFO")
        final_matrix = np.vstack(self.image_matrix)
        
        img = Image.fromarray(final_matrix)
        img = ImageOps.equalize(img) # Melhora o contraste da imagem final.

        output_dir = os.path.join("captures", "images")
        os.makedirs(output_dir, exist_ok=True)

        base_filename = os.path.splitext(os.path.basename(self.wav_filepath))[0]
        output_filepath = os.path.join(output_dir, f"{base_filename}.png")
        
        img.save(output_filepath)
        self.app_state.log(f"✅ Imagem APT salva em: {output_filepath}", "SUCCESS")
        return output_filepath