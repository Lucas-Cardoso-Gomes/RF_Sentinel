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

        # Configura os ganhos individuais do HackRF
        if gain_settings.get("amp_enabled", False):
            sdr.setGain(SOAPY_SDR_RX, 0, "AMP", 1)
            logger.log("Amplificador (AMP) ativado.", "DEBUG")
        else:
            sdr.setGain(SOAPY_SDR_RX, 0, "AMP", 0)

        if "lna_gain" in gain_settings:
            sdr.setGain(SOAPY_SDR_RX, 0, "LNA", gain_settings["lna_gain"])
            logger.log(f"Ganho LNA (IF) configurado para: {gain_settings['lna_gain']} dB", "DEBUG")

        if "vga_gain" in gain_settings:
            sdr.setGain(SOAPY_SDR_RX, 0, "VGA", gain_settings["vga_gain"])
            logger.log(f"Ganho VGA (Baseband) configurado para: {gain_settings['vga_gain']} dB", "DEBUG")

        return True
    except Exception as e:
        logger.log(f"Falha ao configurar o SDR: {e}", "ERROR")
        return False