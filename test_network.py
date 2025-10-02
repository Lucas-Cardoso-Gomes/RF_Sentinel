import requests
import json
from pathlib import Path

# --- Configuration ---
# Manually load the config to get the URL, similar to how the app does it.
CONFIG_PATH = Path("config.json")
if not CONFIG_PATH.exists():
    import shutil
    shutil.copy("config.json.example", CONFIG_PATH)

with open(CONFIG_PATH, "r") as f:
    config_data = json.load(f)

TLE_URL = config_data["noaa"]["tle_url"]

# --- Test ---
print(f"Attempting to download TLE data from: {TLE_URL}")

try:
    # Use a timeout to prevent the script from hanging indefinitely
    response = requests.get(TLE_URL, timeout=20)
    response.raise_for_status()  # Raise an exception for bad status codes (4xx or 5xx)

    print("--- SUCCESS ---")
    print(f"Status Code: {response.status_code}")
    print(f"Downloaded {len(response.text)} bytes.")
    # Print the first few lines of the TLE data
    print("Data preview:")
    print("\n".join(response.text.splitlines()[:6]))

except requests.exceptions.Timeout:
    print("--- FAILURE ---")
    print("Error: The request timed out. The sandbox may not have external network access.")
except requests.exceptions.RequestException as e:
    print("--- FAILURE ---")
    print(f"An error occurred: {e}")
except Exception as e:
    print("--- UNEXPECTED FAILURE ---")
    print(f"An unexpected error occurred: {e}")