# utils/decoder.py
import numpy as np
from scipy.signal import hilbert, resample
from scipy.io import wavfile
from PIL import Image
import os

# --- Constantes para o sinal APT ---
APT_SAMPLING_RATE = 4160  # Taxa de amostragem ideal para linhas APT
APT_LINE_RATE_HZ = 2  # 2 linhas por segundo
APT_SAMPLES_PER_LINE = int(APT_SAMPLING_RATE / APT_LINE_RATE_HZ)
IMAGE_WIDTH_PX = 909  # Largura padrão para imagens APT
SYNC_A_FRAME = [0, 1, 0, 1, 0, 1, 0, 1, 0, 1, 0, 1, 0, 1, 0, 1, 0, 1, 0, 1, 0, 1, 0, 1, 0, 1, 0, 1, 0, 1, 0, 1, 0, 1, 0, 1, 0, 1, 0] # Padrão simplificado

def decode_apt(wav_filepath: str) -> str | None:
    """
    Decodifica um arquivo WAV contendo um sinal APT de um satélite NOAA.

    Args:
        wav_filepath: O caminho para o arquivo .wav capturado.

    Returns:
        O caminho para o arquivo de imagem .png gerado, ou None se ocorrer um erro.
    """
    print(f"🛰️  Iniciando decodificação APT para: {wav_filepath}")
    try:
        # 1. Carregar o arquivo WAV
        samplerate, signal_stereo = wavfile.read(wav_filepath)
        
        # O sinal I/Q está em estéreo, usamos o canal esquerdo (I)
        signal = signal_stereo[:, 0].astype(np.float32)

        # 2. Demodulação AM usando a transformada de Hilbert
        print("    -> Realizando demodulação AM...")
        analytic_signal = hilbert(signal)
        am_demodulated = np.abs(analytic_signal)

        # 3. Reamostragem para a taxa de amostragem APT
        print(f"    -> Reamostrando de {samplerate} Hz para {APT_SAMPLING_RATE} Hz...")
        num_samples_resampled = int(len(am_demodulated) * APT_SAMPLING_RATE / samplerate)
        resampled_signal = resample(am_demodulated, num_samples_resampled)

        # 4. Sincronização e criação da imagem (abordagem simplificada)
        print("    -> Sincronizando e construindo a imagem...")
        
        # Normaliza o sinal para o range de pixels (0-255)
        pixels = (resampled_signal - np.min(resampled_signal)) / (np.max(resampled_signal) - np.min(resampled_signal)) * 255
        pixels = pixels.astype(np.uint8)

        # Divide o sinal em linhas baseadas na taxa de amostragem
        num_lines = len(pixels) // APT_SAMPLES_PER_LINE
        if num_lines == 0:
            print("❌ Erro: Sinal muito curto para formar uma linha de imagem.")
            return None
            
        # Pega o comprimento da linha e trunca os pixels excedentes
        pixels = pixels[:num_lines * APT_SAMPLES_PER_LINE]
        
        # Redimensiona cada linha para a largura da imagem
        image_matrix = np.reshape(pixels, (num_lines, APT_SAMPLES_PER_LINE))
        
        # Usa a biblioteca Pillow para um redimensionamento de melhor qualidade
        img_temp = Image.fromarray(image_matrix)
        img_resized = img_temp.resize((IMAGE_WIDTH_PX, num_lines), Image.LANCZOS)
        
        # 5. Salvar a imagem
        output_dir = "captures/images"
        os.makedirs(output_dir, exist_ok=True)
        base_filename = os.path.splitext(os.path.basename(wav_filepath))[0]
        output_filepath = os.path.join(output_dir, f"{base_filename}.png")
        
        img_resized.save(output_filepath)
        print(f"✅ Imagem APT salva em: {output_filepath}")
        return output_filepath

    except Exception as e:
        print(f"❌ Falha na decodificação APT: {e}")
        return None