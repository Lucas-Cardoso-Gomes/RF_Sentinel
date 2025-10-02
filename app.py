import json
import logging
import os
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

# --- Constants ---
CONFIG_PATH = Path("config.json")
CONFIG_EXAMPLE_PATH = Path("config.json.example")

# --- Application Setup ---
app = FastAPI(
    title="RFSentinel",
    description="An autonomous RF analysis system using HackRF One.",
    version="0.1.0",
)

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


# --- Main Application Logic ---
@app.on_event("startup")
async def startup_event():
    """Tasks to run when the application starts."""
    try:
        # 1. Load Configuration
        config = load_configuration()
        app.state.config = config

        # 2. Setup Logging
        setup_logging(config.logging.level)
        logging.info("RFSentinel application starting up.")
        logging.info("Configuration loaded and validated successfully.")

        # 3. Initialize Database
        initialize_database(str(config.data_paths.db))
        logging.info(f"Database initialized at '{config.data_paths.db}'")

        # 4. Initialize Satellite Tracker
        try:
            tle_manager = TLEManager(config)
            tle_manager.load_satellites()  # Pre-load satellite data
            app.state.tle_manager = tle_manager

            pass_predictor = PassPredictor(config, tle_manager)
            app.state.pass_predictor = pass_predictor

            logging.info("Satellite tracking modules initialized successfully.")
        except Exception as e:
            logging.error(f"Failed to initialize satellite tracker: {e}", exc_info=True)
            app.state.tle_manager = None
            app.state.pass_predictor = None

    except (FileNotFoundError, ValidationError, RuntimeError) as e:
        logging.critical(f"A critical error occurred during startup: {e}", exc_info=True)
        # In a real application, you might want to exit gracefully.
        # For now, we log and let FastAPI handle the shutdown.
        raise

@app.get("/", summary="Root endpoint", description="Provides basic status information.")
async def root():
    """Root endpoint to check if the API is running."""
    return {
        "status": "ok",
        "message": "Welcome to RFSentinel API",
        "version": app.version,
    }

# --- API Endpoints for Tracking ---

@app.get(
    "/tracking/next-pass",
    response_model=Optional[SatellitePass],
    summary="Get the next upcoming satellite pass",
    description="Calculates and returns the details of the very next satellite pass with an elevation greater than the configured minimum.",
)
async def get_next_pass(request: Request):
    """
    Endpoint to get the next satellite pass.
    Returns the pass details or null if no pass is found soon.
    """
    pass_predictor: Optional[PassPredictor] = getattr(request.app.state, 'pass_predictor', None)
    if not pass_predictor:
        # This returns a 500 error by default, which is appropriate
        # if a core component failed to initialize.
        raise Exception("Pass predictor is not available.")

    upcoming_passes = pass_predictor.find_upcoming_passes(hours_ahead=72)
    if not upcoming_passes:
        return None

    return upcoming_passes[0]

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