import subprocess
import numpy as np
import datetime
import wave
import os
import threading

from utils import db
from utils.decoder import RealtimeAPTDecoder
from utils.logger import logger

try:
    from utils.iss_post_process import process_iss_capture
except ImportError:
    process_iss_capture = None

def perform_capture(sdr_unused, target_info):
    """
    Executa a captura de sinal usando hackrf_transfer, delegando o controle de duração
    ao próprio processo para garantir um encerramento limpo e robusto.
    """
    # --- CORREÇÃO DO FUSO HORÁRIO ---
    # Altera de .now() para .utcnow() para guardar o tempo em formato universal
    timestamp = datetime.datetime.utcnow().strftime("%Y-%m-%d_%H-%M-%S")
    filepath = ""
    process = None

    try:
        mode = target_info.get('mode', 'RAW')
        sample_rate = int(target_info.get('sample_rate', 2e6))
        frequency = int(target_info.get('frequency', 100e6))
        duration_sec = target_info['capture_duration_seconds']
        target_name = target_info.get('name', 'capture')
        target_type = target_info.get('type', 'GENERIC')
        lna_gain = target_info.get("lna_gain", 40)
        vga_gain = target_info.get("vga_gain", 30)
        amp_enabled = target_info.get("amp_enabled", True)

        num_samples = int(sample_rate * duration_sec)

        final_filename = f"{target_name.replace(' ', '_')}_{timestamp}_{mode}.wav"
        filepath = os.path.join("captures", final_filename)
        os.makedirs("captures", exist_ok=True)
        
        image_path = None
        decoder = None

        with wave.open(filepath, 'wb') as wf:
            if mode == 'RAW':
                # Dados do HackRF são 8-bit, então o sampwidth é 1
                wf.setnchannels(2)
                wf.setsampwidth(1)
                wf.setframerate(int(sample_rate))
            else:
                wf.setnchannels(1)
                wf.setsampwidth(2)
                wf.setframerate(48000)

            if target_type == 'APT' and mode == 'RAW':
                decoder = RealtimeAPTDecoder(filepath, sample_rate)

            command_list = [
                'hackrf_transfer',
                '-r', '-',
                '-f', str(frequency),
                '-s', str(sample_rate),
                '-n', str(num_samples),
                '-l', str(lna_gain),
                '-g', str(vga_gain),
            ]
            if amp_enabled:
                command_list.extend(['-a', '1'])
            
            command_str = ' '.join(command_list)
            logger.log(f"Iniciando captura controlada por samples: {command_str}", "INFO")

            process = subprocess.Popen(command_str, stdout=subprocess.PIPE, stderr=subprocess.PIPE, shell=False)

            total_bytes_processed = 0
            chunk_size_bytes = 1024 * 512

            while True:
                chunk = process.stdout.read(chunk_size_bytes)
                if not chunk:
                    break

                total_bytes_processed += len(chunk)

                if len(chunk) % 2 != 0:
                    chunk = chunk[:-1]

                if not chunk:
                    continue

                if mode == 'RAW':
                    wf.writeframes(chunk)
                    if decoder:
                        iq_data = np.frombuffer(chunk, dtype=np.int8)
                        iq_data_float = iq_data.astype(np.float32) / 128.0
                        complex_data = iq_data_float[0::2] + 1j * iq_data_float[1::2]
                        decoder.process_chunk(complex_data)
                else:
                    iq_data = np.frombuffer(chunk, dtype=np.int8)
                    iq_data_float = iq_data.astype(np.float32) / 128.0
                    complex_data = iq_data_float[0::2] + 1j * iq_data_float[1::2]
                    x = np.abs(complex_data)
                    x /= np.max(np.abs(x)) if np.max(np.abs(x)) > 0 else 1
                    output_chunk = (x * 32767).astype(np.int16)
                    wf.writeframes(output_chunk.tobytes())

            logger.log(f"Captura finalizada. Total de bytes processados: {total_bytes_processed / (1024*1024):.2f} MB", "SUCCESS")
        
        # O 'with' statement já fechou o ficheiro wf
        if decoder:
            image_path = decoder.finalize()

        db.insert_signal(
            target=target_name, frequency=frequency, timestamp=timestamp, 
            filepath=filepath, image_path=image_path
        )

        if target_type == 'SSTV' and mode == 'RAW' and process_iss_capture:
            logger.log("Captura SSTV detetada. A iniciar pós-processamento...", "INFO")
            processing_thread = threading.Thread(target=process_iss_capture, args=(filepath, sample_rate, logger))
            processing_thread.start()

    except Exception as e:
        logger.log(f"Erro CRÍTICO durante a captura: {e}", "ERROR")

    finally:
        if process:
            try:
                stdout_data, stderr_data = process.communicate(timeout=5)
                stderr_output = stderr_data.decode('utf-8', errors='ignore')
                if stderr_output:
                    logger.log(f"Log do hackrf_transfer:\n{stderr_output}", "DEBUG")
            except subprocess.TimeoutExpired:
                logger.log("O processo hackrf_transfer não terminou a tempo. A forçar o encerramento.", "WARN")
                process.kill()