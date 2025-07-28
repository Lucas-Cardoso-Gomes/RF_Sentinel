# utils/sdr_utils.py
from SoapySDR import *
from utils.logger import logger

def setup_sdr_for_capture(sdr, frequency, sample_rate, gain_settings):
    """
    Configura todos os parâmetros necessários do SDR para uma captura.
    Retorna True em caso de sucesso, False em caso de falha.
    """
    try:
        sdr.setSampleRate(SOAPY_SDR_RX, 0, sample_rate)
        sdr.setFrequency(SOAPY_SDR_RX, 0, frequency)

        # Desativa o ganho automático para ter controle manual
        sdr.setGainMode(SOAPY_SDR_RX, 0, False)

        # Lógica de ganho simplificada e robusta
        if "gain" in gain_settings:
            total_gain = gain_settings["gain"]
            sdr.setGain(SOAPY_SDR_RX, 0, total_gain)
            logger.log(f"Ganho geral configurado para: {total_gain} dB", "DEBUG")
        else:
            # Fallback para o amplificador se a configuração antiga for usada
            if gain_settings.get("amp", 0) == 1:
                sdr.setGain(SOAPY_SDR_RX, 0, "AMP", 1)
                logger.log("Amplificador (AMP) ativado.", "DEBUG")

        return True
    except Exception as e:
        logger.log(f"Falha ao configurar o SDR: {e}", "ERROR")
        return False