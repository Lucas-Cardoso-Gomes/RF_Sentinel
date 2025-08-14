import SoapySDR
import threading
from utils.logger import logger

class SDRManager:
    _instance = None
    _lock = threading.Lock()

    def __new__(cls):
        with cls._lock:
            if cls._instance is None:
                cls._instance = super(SDRManager, cls).__new__(cls)
                cls._instance._initialized = False
        return cls._instance

    def __init__(self):
        if self._initialized: return
        self.sdr = None
        self.device_args = None
        self.lock = threading.Lock()
        self._initialized = True
        logger.log("Gerenciador de SDR inicializado.", "DEBUG")
        self.find_hackrf()

    def find_hackrf(self):
        if self.device_args: return self.device_args
        try:
            devices = SoapySDR.Device.enumerate()
            for dev in devices:
                if "driver" in dev and dev["driver"] == "hackrf":
                    logger.log(f"Dispositivo HackRF encontrado: {dev['label']}", "SUCCESS")
                    self.device_args = dev
                    return self.device_args
            logger.log("Nenhum dispositivo HackRF encontrado na varredura.", "WARN")
        except Exception as e:
            logger.log(f"Erro ao enumerar dispositivos SDR: {e}", "ERROR")
        return None

    def acquire(self):
        """
        Adquire o lock e CRIA uma nova conexão limpa com o SDR.
        """
        logger.log("Tentando adquirir o dispositivo SDR...", "DEBUG")
        self.lock.acquire()
        try:
            if not self.device_args: self.find_hackrf()
            if not self.device_args: raise RuntimeError("Nenhum dispositivo HackRF foi encontrado.")
            
            logger.log(f"Abrindo nova conexão com o dispositivo: {self.device_args['label']}", "INFO")
            self.sdr = SoapySDR.Device(self.device_args)
            
            logger.log("Dispositivo SDR adquirido com sucesso.", "DEBUG")
            return self.sdr
        except Exception as e:
            logger.log(f"Falha ao adquirir/abrir dispositivo SDR: {e}", "ERROR")
            self.lock.release()
            return None

    def release(self, sdr_instance):
        """
        Fecha a conexão com o SDR e libera o lock.
        """
        if sdr_instance is not None:
            logger.log("Fechando conexão com o dispositivo SDR.", "DEBUG")
            sdr_instance = None 
        
        self.sdr = None
        logger.log("Dispositivo SDR liberado.", "DEBUG")
        self.lock.release()

sdr_manager = SDRManager()