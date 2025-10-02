import json
import logging
import os
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Optional

import uvicorn
from fastapi import FastAPI, Request
from pydantic import ValidationError

# --- Project Structure Setup ---
# Ensure the script can find modules in the project root
import sys
sys.path.append(str(Path(__file__).parent))

from core.config import AppConfig
from core.database import initialize_database
from tracking.tle import TLEManager
from tracking.predictor import PassPredictor, SatellitePass
from sdr.hackrf import HackRF

# --- Constants ---
CONFIG_PATH = Path("config.json")
CONFIG_EXAMPLE_PATH = Path("config.json.example")

# --- Configuration Loading ---
def load_configuration() -> AppConfig:
    """
    Loads and validates the configuration from config.json.
    If config.json is missing, it copies it from the example file.
    """
    if not CONFIG_PATH.exists():
        logging.warning(
            f"'{CONFIG_PATH}' not found. "
            f"Creating it from '{CONFIG_EXAMPLE_PATH}'."
        )
        if not CONFIG_EXAMPLE_PATH.exists():
            raise FileNotFoundError(
                f"'{CONFIG_EXAMPLE_PATH}' is missing. Cannot create config."
            )
        import shutil
        shutil.copy(CONFIG_EXAMPLE_PATH, CONFIG_PATH)

    with open(CONFIG_PATH, "r") as f:
        config_data = json.load(f)

    try:
        config = AppConfig.parse_obj(config_data)
    except ValidationError as e:
        logging.error(f"Configuration validation error in '{CONFIG_PATH}': {e}")
        raise

    # Create data directories defined in the config
    os.makedirs(config.data_paths.captures, exist_ok=True)
    os.makedirs(config.data_paths.decoded, exist_ok=True)
    # Ensure the parent directory for the database exists
    os.makedirs(config.data_paths.db.parent, exist_ok=True)


    return config

# --- Logging Setup ---
def setup_logging(log_level: str = "INFO"):
    """Configures the application's logger."""
    logging.basicConfig(
        level=log_level,
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
        handlers=[
            logging.StreamHandler(sys.stdout),
            # Optional: Add a FileHandler here for logging to a file
            # logging.FileHandler("data/rfsentinel.log")
        ],
    )
    logging.getLogger("uvicorn").setLevel(log_level)
    logging.getLogger("uvicorn.access").setLevel(logging.WARNING)


# --- Application Lifespan Management ---
@asynccontextmanager
async def lifespan(app: FastAPI):
    """
    Manages application startup and shutdown events.
    This is the modern replacement for on_event("startup") and on_event("shutdown").
    """
    # --- Startup Logic ---
    logging.info("--- RFSentinel Starting Up ---")

    # 1. Load Configuration
    try:
        app.state.config = load_configuration()
        setup_logging(app.state.config.logging.level)
        logging.info("Configuration loaded and validated successfully.")
    except (FileNotFoundError, ValidationError) as e:
        logging.critical(f"Fatal error during configuration load: {e}", exc_info=True)
        # Prevent app from starting if config is broken
        raise RuntimeError("Configuration failed, cannot start.") from e

    # 2. Initialize Database
    initialize_database(str(app.state.config.data_paths.db))
    logging.info(f"Database initialized at '{app.state.config.data_paths.db}'")

    # 3. Initialize Satellite Tracker
    try:
        tle_manager = TLEManager(app.state.config)
        tle_manager.load_satellites()
        app.state.tle_manager = tle_manager
        app.state.pass_predictor = PassPredictor(app.state.config, tle_manager)
        logging.info("Satellite tracking modules initialized successfully.")
    except Exception as e:
        logging.error(f"Failed to initialize satellite tracker: {e}", exc_info=True)
        app.state.tle_manager = None
        app.state.pass_predictor = None

    # 4. Initialize SDR Device
    sdr_device = HackRF()
    if sdr_device.open():
        logging.info("HackRF device connected successfully.")
        app.state.sdr_device = sdr_device
    else:
        logging.warning("Could not connect to HackRF device. SDR functions will be unavailable.")
        app.state.sdr_device = None

    yield  # --- Application is now running ---

    # --- Shutdown Logic ---
    logging.info("--- RFSentinel Shutting Down ---")
    if app.state.sdr_device:
        app.state.sdr_device.close()

# --- Application Setup ---
app = FastAPI(
    title="RFSentinel",
    description="An autonomous RF analysis system using HackRF One.",
    version="0.1.0",
    lifespan=lifespan,
)

@app.get("/", summary="Root endpoint", description="Provides basic status information.")
async def root():
    """Root endpoint to check if the API is running."""
    return {
        "status": "ok",
        "message": "Welcome to RFSentinel API",
        "version": app.version,
    }

# --- API Endpoints ---

@app.get("/sdr/status", summary="Get SDR device status")
async def get_sdr_status(request: Request):
    """Checks and returns the connection status of the HackRF device."""
    sdr_device: Optional[HackRF] = getattr(request.app.state, 'sdr_device', None)
    if sdr_device and sdr_device.is_open:
        return {"status": "connected", "device_info": "HackRF One"}
    return {"status": "disconnected", "device_info": None}

@app.get(
    "/tracking/next-pass",
    response_model=Optional[SatellitePass],
    summary="Get the next upcoming satellite pass",
)
async def get_next_pass(request: Request):
    """
    Calculates and returns the details of the very next satellite pass
    with an elevation greater than the configured minimum.
    """
    pass_predictor: Optional[PassPredictor] = getattr(request.app.state, 'pass_predictor', None)
    if not pass_predictor:
        raise Exception("Pass predictor is not available.")

    upcoming_passes = pass_predictor.find_upcoming_passes(hours_ahead=72)
    return upcoming_passes[0] if upcoming_passes else None

# --- Main Execution ---
if __name__ == "__main__":
    # This block allows running the app directly with `python app.py`
    # It's useful for development. For production, you would typically
    # use a process manager like Gunicorn or Uvicorn directly.
    uvicorn.run(
        "app:app",
        host="0.0.0.0",
        port=8000,
        reload=True, # Reloads the server on code changes
        log_level="info",
    )