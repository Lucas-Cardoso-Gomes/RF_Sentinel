import time
from skyfield.api import load

print("Attempting to initialize skyfield's timescale...")
print(f"Start time: {time.time()}")

try:
    # This operation might trigger an automatic download of ephemeris files
    # if they are not already cached.
    ts = load.timescale()

    print("\n--- SUCCESS ---")
    print("skyfield.api.load.timescale() completed successfully.")
    print(f"Current time from skyfield: {ts.now().utc_iso()}")

except Exception as e:
    print("\n--- FAILURE ---")
    print(f"An error occurred during timescale initialization: {e}")

finally:
    print(f"End time: {time.time()}")