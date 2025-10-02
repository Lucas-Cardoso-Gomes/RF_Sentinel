import logging

# This module provides a resilient wrapper for the HackRF SDR.
# It attempts to import the necessary libraries but falls back to a "dummy" class
# if the drivers are not installed. This allows the application to run
# without a functional SDR.

HACKRF_ENABLED = False
try:
    from hackrf import HackRF as PyHackRF, HackRFError
    HACKRF_ENABLED = True
except (ImportError, OSError) as e:
    # This catches both missing 'pyhackrf' and missing 'libhackrf.so'
    logging.warning(
        f"Could not import HackRF libraries: {e}. "
        "SDR functionality will be disabled."
    )
    # Define placeholder classes so the rest of the app doesn't crash
    class PyHackRF: pass
    class HackRFError(Exception): pass


class HackRF:
    """
    A high-level wrapper for the HackRF One SDR.
    If the necessary drivers are not found, it acts as a dummy interface
    that prevents the application from crashing.
    """
    def __init__(self):
        self.device: PyHackRF | None = None
        self.is_open = False
        if not HACKRF_ENABLED:
            logging.info("HackRF is disabled (drivers not found).")

    def open(self) -> bool:
        """
        Finds and initializes a connection to the HackRF One device.
        Returns False if drivers are not enabled or if the device is not found.
        """
        if not HACKRF_ENABLED:
            return False
        if self.is_open:
            logging.warning("HackRF device is already open.")
            return True
        try:
            logging.info("Attempting to open HackRF device...")
            self.device = PyHackRF()
            self.is_open = True
            logging.info("HackRF device opened successfully.")
            return True
        except HackRFError as e:
            # This error means the library is present, but the device is not connected
            # or there's a permission issue.
            logging.error(f"Failed to open HackRF device: {e}")
            self.device = None
            self.is_open = False
            return False

    def close(self):
        """Closes the connection to the HackRF One device."""
        if self.device and self.is_open:
            logging.info("Closing HackRF device.")
            self.device.close()
        self.device = None
        self.is_open = False

    def _check_open(self):
        if not self.is_open or not self.device:
            raise HackRFError("Device is not open or not available.")

    def set_frequency(self, freq_hz: int):
        self._check_open()
        logging.debug(f"Setting center frequency to {freq_hz / 1e6:.2f} MHz")
        self.device.center_freq = freq_hz

    def set_sample_rate(self, sample_rate_hz: int):
        self._check_open()
        logging.debug(f"Setting sample rate to {sample_rate_hz / 1e6:.2f} MHz")
        self.device.sample_rate = sample_rate_hz

    def set_lna_gain(self, gain_db: int):
        self._check_open()
        logging.debug(f"Setting LNA gain to {gain_db} dB")
        self.device.lna_gain = gain_db

    def set_vga_gain(self, gain_db: int):
        self._check_open()
        logging.debug(f"Setting VGA gain to {gain_db} dB")
        self.device.vga_gain = gain_db

    def start_rx_stream(self, callback):
        self._check_open()
        logging.info("Starting RX stream...")
        # self.device.start_rx(callback) # To be implemented
        pass

    def stop_rx_stream(self):
        if not self.is_open or not self.device: return
        logging.info("Stopping RX stream...")
        # self.device.stop_rx() # To be implemented
        pass

    def __enter__(self):
        self.open()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.close()