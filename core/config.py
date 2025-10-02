from pydantic import BaseModel, Field, HttpUrl
from pathlib import Path

# --- Pydantic Models for Configuration ---

class StationConfig(BaseModel):
    """Defines the geographic location of the ground station."""
    latitude: float = Field(..., ge=-90, le=90, description="Latitude in decimal degrees.")
    longitude: float = Field(..., ge=-180, le=180, description="Longitude in decimal degrees.")
    elevation_m: int = Field(..., description="Elevation in meters above sea level.")

class SdrConfig(BaseModel):
    """Defines settings for the SDR hardware."""
    gain_lna: int = Field(..., ge=0, le=40, description="LNA (low-noise amplifier) gain in dB.")
    gain_vga: int = Field(..., ge=0, le=62, description="VGA (variable-gain amplifier) gain in dB.")

class NoaaConfig(BaseModel):
    """Defines settings for NOAA satellite tracking and decoding."""
    tle_url: HttpUrl = Field(..., description="URL for downloading TLE data for NOAA satellites.")
    tle_cache_days: int = Field(1, gt=0, description="Number of days to cache the TLE file.")
    min_elevation_deg: float = Field(25.0, ge=0, le=90, description="Minimum satellite elevation for a pass to be considered for capture.")
    apt_bandwidth_hz: int = Field(40000, gt=0, description="Bandwidth for APT signal capture.")

class IdleScanConfig(BaseModel):
    """Defines settings for the idle scanning mode."""
    step_mhz: int = Field(20, gt=0, description="Frequency step in MHz for each scan block.")
    duration_s: int = Field(10, gt=0, description="Duration in seconds for each scan block capture.")

class DataPathsConfig(BaseModel):
    """Defines the directory structure for storing data."""
    base: Path = Field("data", description="Base directory for all data.")
    captures: Path = Field("data/captures", description="Directory for raw IQ and WAV captures.")
    decoded: Path = Field("data/decoded", description="Directory for decoded images and data.")
    db: Path = Field("data/rfsentinel.db", description="Path to the SQLite database file.")

class LoggingConfig(BaseModel):
    """Defines logging settings."""
    level: str = Field("INFO", pattern=r"^(DEBUG|INFO|WARNING|ERROR|CRITICAL)$", description="Logging level.")

class AppConfig(BaseModel):
    """The main configuration model for the entire application."""
    station: StationConfig
    sdr: SdrConfig
    noaa: NoaaConfig
    idle_scan: IdleScanConfig = Field(..., alias="idle_scan")
    data_paths: DataPathsConfig = Field(..., alias="data_paths")
    logging: LoggingConfig