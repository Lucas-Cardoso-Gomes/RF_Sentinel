# utils/scanner.py
import subprocess
import numpy as np
import datetime
import wave
import os
import time

from utils import db
from utils.decoder import RealtimeAPTDecoder
from utils.logger import logger

def perform_capture(sdr_unused, target_info):
    """
    Executa a captura de sinal usando hackrf_transfer com streaming para o Python,
    combinando estabilidade e eficiência de memória.
    """
    timestamp = datetime.datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
    filepath = ""
    process = None

    try:
        # --- Parâmetros ---
        mode = target_info.get('mode', 'RAW')
        sample_rate = int(target_info.get('sample_rate', 2e6))
        frequency = int(target_info.get('frequency', 100e6))
        duration_sec = target_info['capture_duration_seconds']
        target_name = target_info.get('name', 'capture')
        lna_gain = target_info.get("lna_gain", 40)
        vga_gain = target_info.get("vga_gain", 30)
        amp_enabled = target_info.get("amp_enabled", True)

        # --- Prepara o arquivo WAV de saída ---
        final_filename = f"{target_name.replace(' ', '_')}_{timestamp}_{mode}.wav"
        filepath = os.path.join("captures", final_filename)
        os.makedirs("captures", exist_ok=True)
        
        wf = wave.open(filepath, 'wb')
        audio_sample_rate = 48000
        if mode == 'RAW':
            wf.setnchannels(2); wf.setsampwidth(2); wf.setframerate(int(sample_rate))
        else: # AM ou FM
            wf.setnchannels(1); wf.setsampwidth(2); wf.setframerate(audio_sample_rate)

        # --- Prepara o decodificador em tempo real se for NOAA ---
        decoder = None
        if "NOAA" in target_name and mode == 'RAW':
            decoder = RealtimeAPTDecoder(filepath, sample_rate)

        # --- Constrói o Comando e Inicia o Subprocesso ---
        command_list = [
            'hackrf_transfer',
            '-r', '-',  # Envia dados brutos para a saída padrão (stdout)
            '-f', str(frequency),
            '-s', str(sample_rate),
            '-l', str(lna_gain),
            '-g', str(vga_gain),
        ]
        if amp_enabled:
            command_list.extend(['-a', '1'])
        
        command_str = ' '.join(command_list)
        logger.log(f"Iniciando captura via pipe: {command_str}", "INFO")

        process = subprocess.Popen(command_str, stdout=subprocess.PIPE, stderr=subprocess.PIPE, shell=True)
        
        start_time = time.time()
        total_bytes_processed = 0
        chunk_size_bytes = 1024 * 512 # Processa em chunks de 512KB

        while True:
            # Verifica se a duração da captura foi atingida
            if time.time() - start_time > duration_sec:
                logger.log(f"Tempo de captura de {duration_sec}s atingido. Finalizando...", "INFO")
                break

            chunk = process.stdout.read(chunk_size_bytes)
            if not chunk:
                break
            
            total_bytes_processed += len(chunk)
            
            # --- Processamento do Chunk ---
            iq_data = np.frombuffer(chunk, dtype=np.int8)
            iq_data_float = iq_data.astype(np.float32) / 128.0
            complex_data = iq_data_float[0::2] + 1j * iq_data_float[1::2]
            
            # Processa e escreve o áudio
            if mode == 'RAW':
                samples_real = (np.real(complex_data) * 32767).astype(np.int16)
                samples_imag = (np.imag(complex_data) * 32767).astype(np.int16)
                output_chunk = np.vstack((samples_real, samples_imag)).T
            else: # AM ou FM
                # Implementação simplificada para streaming, pode ser aprimorada
                x = np.abs(complex_data)
                x /= np.max(np.abs(x)) if np.max(np.abs(x)) > 0 else 1
                output_chunk = (x * 32767).astype(np.int16)

            wf.writeframes(output_chunk.tobytes())

            # Se for um NOAA, processa o chunk para a imagem
            if decoder:
                decoder.process_chunk(complex_data)

        logger.log(f"Captura finalizada. Total de bytes processados: {total_bytes_processed / (1024*1024):.2f} MB", "SUCCESS")
        
        # --- Finaliza tudo ---
        wf.close()
        image_path = None
        if decoder:
            image_path = decoder.finalize()
        
        db.insert_signal(
            target=target_name, frequency=frequency, timestamp=timestamp, 
            filepath=filepath, image_path=image_path
        )

    except Exception as e:
        logger.log(f"Erro CRÍTICO durante a captura: {e}", "ERROR")

    finally:
        if process:
            # Garante que o processo hackrf_transfer seja encerrado
            if process.poll() is None:
                logger.log("Encerrando processo hackrf_transfer...", "DEBUG")
                process.terminate()
                process.wait()
            
            # Exibe erros do hackrf_transfer, se houver
            stderr_output = process.stderr.read().decode('utf-8', errors='ignore')
            if stderr_output:
                logger.log(f"Saída de erro do hackrf_transfer: {stderr_output}", "WARN")