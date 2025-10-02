# RFSentinel

**RFSentinel** is an autonomous RF analysis system designed to operate with a HackRF One SDR. It provides a comprehensive solution for monitoring the radio spectrum, with a special focus on automated satellite signal acquisition and decoding.

## Core Features

The system operates in three distinct modes, managed by a priority-based scheduler:

1.  **Priority Mode (NOAA Satellites)**: Automatically tracks NOAA satellites broadcasting on APT (Automatic Picture Transmission) frequencies (~137 MHz). When a satellite is predicted to pass over the configured station location, RFSentinel interrupts other tasks to tune to the correct frequency, record the transmission, decode the APT signal into a visual image, and save the image with relevant metadata.

2.  **Manual Mode**: Allows a user to perform on-demand RF captures via a CLI or a REST API. The user can specify parameters such as frequency, sample rate, gain, and capture duration. This mode is ideal for targeted analysis and signal recording.

3.  **Idle Mode**: When no priority or manual tasks are active, the system enters an idle state, performing a wideband scan of the RF spectrum. It sweeps through predefined frequency ranges, captures short IQ samples, and performs basic signal analysis to detect and classify signals of interest, generating reports for later review.

## Technical Stack

- **Hardware**: HackRF One
- **Primary Language**: Python 3
- **Core Libraries**:
    - **SDR Control**: `pyhackrf` for native HackRF One interfacing.
    - **API**: `FastAPI` for a high-performance REST API.
    - **Satellite Tracking**: `skyfield` for TLE-based pass prediction.
    - **Signal Processing**: `numpy`, `scipy`.
    - **APT Decoding**: `noaa-apt`.
    - **Database**: `SQLite` for metadata storage.
- **Deployment**: Docker & systemd.

## Project Structure

```
rfsentinel/
├── app.py                # Main application entry point
├── cli.py                # Command-line interface
├── api/                  # FastAPI REST API
├── core/                 # Core logic (config, db, scheduler)
├── processing/           # Signal processing (APT, demodulators)
├── sdr/                  # SDR hardware interface
├── tracking/             # Satellite tracking logic
├── data/                 # Captured data, logs, decoded images
├── tests/                # Unit and integration tests
├── config.json.example   # Example configuration file
├── requirements.txt      # Python dependencies
├── Dockerfile
├── rfsentinel.service    # systemd service file
└── README.md
```