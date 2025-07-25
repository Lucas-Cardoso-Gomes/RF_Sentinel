# utils/analyzer.py
import numpy as np
from scipy.io import wavfile
from scipy.signal import spectrogram

def analyze_wav_file(filepath: str):
    """
    Lê um arquivo .wav, calcula seu espectrograma e retorna os dados para visualização.
    """
    try:
        print(f"🔬 Analisando arquivo: {filepath}")
        samplerate, signal_stereo = wavfile.read(filepath)
        
        # Usa apenas um canal (I) para a análise
        signal = signal_stereo[:, 0].astype(np.float32)

        # Calcula o espectrograma
        # nperseg define a resolução da FFT (eixo da frequência)
        # noverlap define a sobreposição para suavizar o eixo do tempo
        f, t, sxx = spectrogram(signal, fs=samplerate, nperseg=1024, noverlap=256)

        # Converte a potência para decibéis (dB)
        sxx_db = 10 * np.log10(sxx + 1e-12) # Adiciona epsilon para evitar log(0)

        return {
            "frequencies": f.tolist(),
            "times": t.tolist(),
            "spectrogram_db": sxx_db.tolist(),
            "samplerate": samplerate,
            "duration": signal.shape[0] / samplerate
        }
    except Exception as e:
        print(f"❌ Erro ao analisar o arquivo {filepath}: {e}")
        return None