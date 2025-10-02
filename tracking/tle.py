import datetime
import logging
from pathlib import Path
from typing import Dict

import requests
from skyfield.api import load, EarthSatellite

# --- Constants ---
TLE_CACHE_FILENAME = "noaa_tle.txt"

class TLEManager:
    """
    Manages the downloading, caching, and loading of TLE (Two-Line Element)
    data for satellites.
    """

    def __init__(self, config):
        """
        Initializes the TLEManager with application configuration.

        Args:
            config (AppConfig): The application's configuration object.
        """
        self.tle_url = str(config.noaa.tle_url)
        self.cache_duration = datetime.timedelta(days=config.noaa.tle_cache_days)

        # The cache file will be stored in the base data directory
        self.cache_file_path = config.data_paths.base / TLE_CACHE_FILENAME

        self.timescale = load.timescale()
        self.satellites: Dict[str, EarthSatellite] = {}

    def _is_cache_valid(self) -> bool:
        """Checks if the cached TLE file exists and is within the cache duration."""
        if not self.cache_file_path.exists():
            logging.info("TLE cache file does not exist.")
            return False

        file_mod_time = datetime.datetime.fromtimestamp(self.cache_file_path.stat().st_mtime)
        if datetime.datetime.now() - file_mod_time > self.cache_duration:
            logging.info("TLE cache has expired.")
            return False

        logging.debug("Using valid TLE cache.")
        return True

    def _download_tle_data(self) -> str:
        """Downloads fresh TLE data from the configured URL."""
        logging.info(f"Downloading fresh TLE data from {self.tle_url}")
        try:
            response = requests.get(self.tle_url, timeout=15)
            response.raise_for_status()  # Raise an exception for bad status codes

            tle_data = response.text

            # Save the fresh data to the cache file
            with open(self.cache_file_path, "w") as f:
                f.write(tle_data)
            logging.info(f"TLE data cached successfully at {self.cache_file_path}")

            return tle_data
        except requests.RequestException as e:
            logging.error(f"Failed to download TLE data: {e}")
            # If download fails, try to use expired cache as a fallback
            if self.cache_file_path.exists():
                logging.warning("Falling back to using expired TLE cache.")
                with open(self.cache_file_path, "r") as f:
                    return f.read()
            raise  # Re-raise if there's no cache at all

    def load_satellites(self) -> Dict[str, EarthSatellite]:
        """
        Loads NOAA satellites from the TLE data.
        It uses cached data if valid, otherwise downloads fresh data.

        Returns:
            A dictionary mapping satellite names to EarthSatellite objects.
        """
        if not self._is_cache_valid():
            tle_data = self._download_tle_data()
        else:
            with open(self.cache_file_path, "r") as f:
                tle_data = f.read()

        # skyfield's load.tle_file expects a string path, not a Path object.
        sats = load.tle_file(str(self.cache_file_path))
        self.satellites = {sat.name: sat for sat in sats}

        logging.info(f"Loaded {len(self.satellites)} satellites: {list(self.satellites.keys())}")
        return self.satellites