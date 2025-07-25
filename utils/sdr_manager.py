# utils/sdr_manager.py
import SoapySDR
from SoapySDR import *
import threading
import time

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
        if self._initialized:
            return
        
        self.sdr = None
        self.active_stream = None
        self.device_args = None
        self.usage_count = 0
        self.lock = threading.Lock()
        self._initialized = True
        print("✔️ Gerenciador de SDR inicializado.")
        
    def find_hackrf(self):
        """Procura por um dispositivo HackRF e armazena seus argumentos."""
        if self.device_args:
            return self.device_args
        
        # --- LOGS DE DEPURAÇÃO ADICIONADOS ---
        print("\n--- [DEBUG SDRManager: find_hackrf] ---")
        try:
            devices = SoapySDR.Device.enumerate()
            if not devices:
                print("DEBUG: SoapySDR.Device.enumerate() retornou uma lista VAZIA.")
                return None

            print(f"DEBUG: SoapySDR encontrou {len(devices)} dispositivo(s):")
            for i, dev in enumerate(devices):
                print(f"  - Dispositivo #{i}: {dev}")
                # Verifica se a chave 'driver' existe antes de acessá-la
                if "driver" in dev and dev["driver"] == "hackrf":
                    print(f"    └──> ✔️ HackRF encontrado! Armazenando argumentos.")
                    self.device_args = dev
                    return self.device_args
            
            print("DEBUG: Nenhum dispositivo com 'driver=hackrf' foi encontrado na lista.")

        except Exception as e:
            print(f"DEBUG: Uma exceção ocorreu durante SoapySDR.Device.enumerate(): {e}")
        
        print("--- [FIM DEBUG] ---\n")
        return None

    def acquire_device(self):
        """Adquire um bloqueio e abre o dispositivo SDR."""
        self.lock.acquire()
        self.usage_count += 1
        
        if self.sdr is None:
            try:
                device_args = self.find_hackrf()
                if not device_args:
                    print("❌ SDRManager: Nenhum HackRF encontrado para aquisição.")
                    self.release_device()
                    return None
                
                print("🔌 SDRManager: Abrindo conexão com o HackRF...")
                self.sdr = SoapySDR.Device(device_args)
            except Exception as e:
                print(f"❌ SDRManager: Falha ao abrir o dispositivo: {e}")
                self.sdr = None
                self.release_device()
                return None
        
        return self.sdr

    def release_device(self):
        """Libera o dispositivo se não estiver mais em uso."""
        self.usage_count -= 1
        if self.usage_count <= 0:
            if self.sdr is not None:
                print("🔌 SDRManager: Fechando conexão com o HackRF.")
                if self.active_stream is not None:
                    try:
                        self.sdr.deactivateStream(self.active_stream)
                        self.sdr.closeStream(self.active_stream)
                    except Exception: pass
                self.active_stream = None
                self.sdr = None
            self.usage_count = 0
        
        self.lock.release()

sdr_manager = SDRManager()